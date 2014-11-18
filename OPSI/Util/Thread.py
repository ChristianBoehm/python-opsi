#!/usr/bin/python
# -*- coding: utf-8 -*-

# This module is part of the desktop management solution opsi
# (open pc server integration) http://www.opsi.org

# Copyright (C) 2010-2014 uib GmbH - http://www.uib.de/

# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.

# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.

# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
opsi python library - Thread

:copyright:  uib GmbH <info@uib.de>
:author: Christian Kampka <c.kampka@uib.de>
:author: Jan Schneider <j.schneider@uib.de>
:author: Niko Wenselowski <n.wenselowski@uib.de>
:license: GNU Affero General Public License version 3
"""

__version__ = '4.0.5.3'

import threading
import inspect
import ctypes
from Queue import Queue, Empty

from OPSI.Logger import Logger

logger = Logger()
GlobalPool = None


class ThreadPoolException(Exception):
	pass


def getGlobalThreadPool(*args, **kwargs):
	global GlobalPool
	if not GlobalPool:
		GlobalPool = ThreadPool(*args, **kwargs)
	else:
		size = kwargs.get('size', 0)
		GlobalPool.increaseUsageCount()
		if GlobalPool.size < size:
			GlobalPool.adjustSize(size)

	return GlobalPool


def _async_raise(tid, exctype):
	"""raises the exception, performs cleanup if needed"""
	if not inspect.isclass(exctype):
		raise TypeError("Only types can be raised (not instances)")

	res = ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(tid), ctypes.py_object(exctype))
	if res == 0:
		logger.warning("Invalid thread id {0}".format(tid))
		return
	elif res != 1:
		# if it returns a number greater than one, you're in trouble,
		# and you should call it again with exc=NULL to revert the effect
		ctypes.pythonapi.PyThreadState_SetAsyncExc(ctypes.c_long(tid), 0)
		raise SystemError("PyThreadState_SetAsyncExc failed")


class KillableThread(threading.Thread):
	def _get_my_tid(self):
		"""determines this (self's) thread id"""
		# do we have it cached?
		if hasattr(self, "_thread_id"):
			return self._thread_id

		# no, look for it in the _active dict
		for tid, tobj in threading._active.items():
			if tobj is self:
				self._thread_id = tid
				return tid

		logger.warning(u"Cannot terminate, could not determine the thread's id")

	def raise_exc(self, exctype):
		"""raises the given exception type in the context of this thread"""
		_async_raise(self._get_my_tid(), exctype)

	def terminate(self):
		"""raises SystemExit in the context of the given thread, which should
		cause the thread to exit silently (unless caught)"""
		if not self.isAlive():
			logger.debug(u"Cannot terminate, thread must be started")
			return
		self.raise_exc(SystemExit)


class ThreadPool(object):

	def __init__(self, size = 20, autostart = True):
		self.size = int(size)
		self.started = False
		self.worker = []
		self.workerLock = threading.Lock()
		self.jobQueue = Queue()
		self.usageCount = 1
		if autostart:
			self.start()

	def increaseUsageCount(self):
		self.usageCount += 1

	def decreaseUsageCount(self):
		self.usageCount -= 1
		if self.usageCount <= 0:
			self.stop()

	free = decreaseUsageCount

	def start(self):
		self.started = True
		self.adjustSize(self.size)

	def adjustSize(self, size):
		size = int(size)
		self.workerLock.acquire()
		try:
			if (size < 1):
				raise ThreadPoolException(u"Threadpool size %d is invalid" % size)

			self.size = size
			if self.started:
				if len(self.worker) > self.size:
					self.__deleteWorkers(num=len(self.worker) - self.size)
				if len(self.worker) < self.size:
					self.__createWorkers(num=self.size - len(self.worker))
		finally:
			self.workerLock.release()

	def __deleteWorker(self, wait=False):
		logger.debug(u"Deleting a worker")
		self.__deleteWorkers(1, wait=wait)

	def __deleteWorkers(self, num, wait=False):
		logger.debug(u"Deleting %d workers" % num)
		deleteWorkers = []
		for worker in self.worker:
			if not worker.busy and not worker in deleteWorkers:
				deleteWorkers.append(worker)
				worker.stop()
				num -= 1
				if num == 0:
					break

		if num > 0:
			for worker in self.worker:
				if not worker in deleteWorkers:
					deleteWorkers.append(worker)
					worker.stop()
					num -= 1
					if num == 0:
						break

		worker_ = []
		for worker in self.worker:
			if not worker in deleteWorkers:
				worker_.append(worker)
		self.worker = worker_
		if wait:
			for worker in deleteWorkers:
				worker.join(60)

	def __createWorker(self):
		logger.debug(u"Creating new worker %s" % (len(self.worker)+1))
		self.__createWorkers(1)

	def __createWorkers(self, num):
		logger.debug(u"Creating %d new workers" % num)
		newWorkers = []
		while (num > 0):
			worker = Worker(self, len(self.worker)+1)
			self.worker.append(worker)
			newWorkers.append(worker)
			num -= 1

	def addJob(self, function, callback = None, *args, **kwargs):
		logger.debug(u"New job added: %s(%s, %s)"% (callback, args, kwargs))
		if not self.started:
			raise ThreadPoolException(u"Pool is not running.")
		self.jobQueue.put( (function, callback, args, kwargs) )

	def stop(self):
		logger.debug(u"Stopping ThreadPool")
		self.workerLock.acquire()
		self.started = False
		try:
			self.__deleteWorkers(num=len(self.worker), wait=True)
		finally:
			self.workerLock.release()


class Worker(threading.Thread):
	def __init__(self, threadPool, name=None):
		threading.Thread.__init__(self, name=name)
		self.threadPool = threadPool
		self.name = name
		self.busy = False
		self.stopped = False
		self.start()

	def run(self):
		while True:
			if self.stopped:
				break
			try:
				object = self.threadPool.jobQueue.get(block=True, timeout=1)
				if object:
					self.busy = True
					(function, callback, args, kwargs) = object
					success = False
					try:
						result = function(*args, **kwargs)
						success = True
						errors = None
					except Exception as e:
						logger.debug(e)
						result = None
						errors = e

					if callback:
						callback(success, result, errors)
					self.threadPool.jobQueue.task_done()
					self.busy = False
			except Empty:
				pass

	def stop(self):
		self.stopped = True
