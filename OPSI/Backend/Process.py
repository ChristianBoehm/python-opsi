#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = = = = = = =
   =   opsi configuration daemon (opsiconfd)   =
   = = = = = = = = = = = = = = = = = = = = = = =
   
   opsiconfd is part of the desktop management solution opsi
   (open pc server integration) http://www.opsi.org
   
   Copyright (C) 2010 uib GmbH
   
   http://www.uib.de/
   
   All rights reserved.
   
   This program is free software; you can redistribute it and/or modify
   it under the terms of the GNU General Public License version 2 as
   published by the Free Software Foundation.
   
   This program is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
   GNU General Public License for more details.
   
   You should have received a copy of the GNU General Public License
   along with this program; if not, write to the Free Software
   Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
   
   @copyright:	uib GmbH <info@uib.de>
   @author: Christian Kampka <c.kampka@uib.de>
   @license: GNU General Public License version 2
"""

import re, os, time, functools, base64
from hashlib import md5

from twisted.application.service import Service
from twisted.internet.protocol import Protocol
from twisted.internet import reactor, defer
from twisted.internet.task import LoopingCall
from twisted.conch.ssh import keys
from twisted.python.failure import Failure

from OPSI.Backend.BackendManager import BackendManager, backendManagerFactory
from OPSI.Service.Process import OpsiPyDaemon
from OPSI.Util.Configuration import BaseConfiguration
from OPSI.Util.amp import OpsiProcessProtocolFactory, RemoteDaemonProxy, OpsiProcessConnector, USE_BUFFERED_RESPONSE
from OPSI.Service.JsonRpc import JsonRpcRequestProcessor
from OPSI.Logger import *
logger = Logger()


class BackendProcessConfiguration(BaseConfiguration):
	
	def _makeParser(self):
		parser = BaseConfiguration._makeParser(self)
		
		parser.add_option("--socket", dest="socket")
		parser.add_option("--logFile", dest="logFile")
		return parser

class BackendDataExchangeProtocol(Protocol):
	
	def dataReceived(self, data):
		pass
	
	def write(self, data):
		self.transport.write(data)

class OpsiBackendService(Service):
	
	def __init__(self, config):
		self._config = config
		
		self._backendManager = None
		self._socket = None
		self._lastPingReceived = time.time()
		self._check = LoopingCall(self.checkConnected)
	
	def checkConnected(self):
		if ((time.time() - self._lastPingReceived) > 30):
			reactor.stop()
	
	def setLogging(self, console=LOG_WARNING, file=LOG_WARNING):
		logger.setConsoleLevel(console)
		logger.setFileLevel(file)
	
	def startService(self):
		logger.info(u"Starting opsi backend Service")
		logger.setLogFile(self._config.logFile)

		if not os.path.exists(os.path.dirname(self._config.socket)):
			os.makedirs(os.path.dirname(self._config.socket))
		
		logger.info(u"Opening socket %s for interprocess communication." % self._config.socket)
		self._socket = reactor.listenUNIX(self._config.socket, OpsiProcessProtocolFactory(self, "%s.dataport" % self._config.socket))
		self._check.start(10)

	def initialize(self, user, password, dispatchConfigFile, backendConfigDir,
				extensionConfigDir, aclFile, depotId, postpath):
		
		self.user = user
		self.password = password
		
		self._backend = BackendManager(
			dispatchConfigFile = dispatchConfigFile,
			backendConfigDir   = backendConfigDir,
			extensionConfigDir = extensionConfigDir,
			depotBackend       = bool(depotId)
		)
		
		modules = self._backend.backend_info()['modules']
		publicKey = keys.Key.fromString(data = base64.decodestring('AAAAB3NzaC1yc2EAAAADAQABAAABAQCAD/I79Jd0eKwwfuVwh5B2z+S8aV0C5suItJa18RrYip+d4P0ogzqoCfOoVWtDojY96FDYv+2d73LsoOckHCnuh55GA0mtuVMWdXNZIE8Avt/RzbEoYGo/H0weuga7I8PuQNC/nyS8w3W8TH4pt+ZCjZZoX8S+IizWCYwfqYoYTMLgB0i+6TCAfJj3mNgCrDZkQ24+rOFS4a8RrjamEz/b81noWl9IntllK1hySkR+LbulfTGALHgHkDUlk0OSu+zBPw/hcDSOMiDQvvHfmR4quGyLPbQ2FOVm1TzE0bQPR+Bhx4V8Eo2kNYstG2eJELrz7J1TJI0rCjpB+FQjYPsP')).keyObject
		data = u''; mks = modules.keys(); mks.sort()
		for module in mks:
			if module in ('valid', 'signature'):
				continue
			val = modules[module]
			if (val == False): val = 'no'
			if (val == True):  val = 'yes'
			data += u'%s = %s\r\n' % (module.lower().strip(), val)
		if not bool(publicKey.verify(md5(data).digest(), [ long(modules['signature']) ])) or \
			not modules.get('high_availability'):
			raise Exception(u"Failed to verify modules signature")
		
		
		self._backendManager = backendManagerFactory(
			user               = user,
			password           = password,
			dispatchConfigFile = dispatchConfigFile,
			backendConfigDir   = backendConfigDir,
			extensionConfigDir = extensionConfigDir,
			aclFile            = aclFile,
			depotId            = depotId,
			postpath           = postpath,
			context            = self._backend
		)
	
	def stopService(self):
		self._check.stop()
		
		if self._backend:
			self._backend.backend_exit()
		if self._backendManager:
			self._backendManager.backend_exit()
		if self._socket is not None:
			d = self._socket.stopListening()
			d.addCallback(lambda x: self._cleanup)
			
	def _cleanup(self):
		if os.path.exists(self._socket):
			os.unlink(self._socket)
	
	def processQuery(self, query, gzip=False):
		decoder = JsonRpcRequestProcessor(query, self._backendManager, gzip=gzip)
		decoder.decodeQuery()
		decoder.buildRpcs()
		d = decoder.executeRpcs(False)
		d.addCallback(lambda x: decoder.getResults())
		return d
	
	def isRunning(self):
		self._lastPingReceived = time.time()
		return True
	
	def __getattr__(self, name):
		if self._backendManager is not None:
			return getattr(self._backendManager, name, None)
	
	
class OpsiBackendProcess(OpsiPyDaemon):
	
	user = "opsiconfd"
	serviceClass = OpsiBackendService
	configurationClass = BackendProcessConfiguration
	allowRestart = False
	
	def __init__(self, socket, args=[], reactor=reactor, logFile = logger.getLogFile()):
		
		args.extend(["--socket", socket, "--logFile", logFile])
		OpsiPyDaemon.__init__(self, socket = socket, args = args, reactor = reactor)
		self._uid, self._gid = None, None
		
		self.check = LoopingCall(self.checkRunning)
	
	def start(self):
		logger.info(u"Starting new backend worker process")
		OpsiPyDaemon.start(self)
		self.check.start(10, False)
	
	def checkRunning(self):
		d = self.isRunning()
		d.addCallback(self.restart)

	def restart(self, isRunning):
		if not isRunning and self.allowRestart:
			d = self.stop()
			d.addCallback(lambda x: self.start)
	
	def processQuery(self, request, gzip=False):
		d = self.callRemote("processQuery", request, gzip=gzip)
		d.addCallback(self.maybeStopped)
		return d
	
	def maybeStopped(self, result):
		r = defer.Deferred()
		if 'backend_exit' in map((lambda x: x.method), result):
				d = self.stop()
				d.addCallback(lambda x: r.callback(result))
		else:
			r.callback(result)
		return r
	
	def stop(self):
		logger.info(u"Stopping backend worker process (pid: %s)" % self._process.pid)
		result = defer.Deferred()
		try:
			self.check.stop()
		except Exception, e:
			logger.error(e)
			result.errback(Failure())
		
		d = OpsiPyDaemon.stop(self)
		d.addCallback(result.callback, result.errback)
		return result
	
	def backend_exit(self):
		print "BACKEND_EXIT"
		d = self.callRemote("backend_exit")
		d.addCallback(lambda x: self.stop())
		return d
	
	def __getattr__(self, name):
		logger.debug("Generating method '%s' on the fly." % name)
		return functools.partial(self.callRemote, name)


