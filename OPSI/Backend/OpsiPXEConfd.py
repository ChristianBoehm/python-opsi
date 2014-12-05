#! /usr/bin/env python
# -*- coding: utf-8 -*-

# This file is part of python-opsi.
# Copyright (C) 2010-2014 uib GmbH <info@uib.de>
# All rights reserved.

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
OpsiPXEConfd-Backend

:copyright:	uib GmbH <info@uib.de>
:author: Jan Schneider <j.schneider@uib.de>
:author: Niko Wenselowski <n.wenselowski@uib.de>
:license: GNU Affero General Public License version 3
"""

__version__ = '4.0.0.1'

# Imports
import socket, threading, time

# OPSI imports
from OPSI.Logger import *
from OPSI.Types import *
from OPSI.Object import *
from OPSI.Backend.Backend import *
from OPSI.Backend.JSONRPC import JSONRPCBackend
from OPSI.Util import getfqdn
# Get logger instance
logger = Logger()


# ======================================================================================================
# =                                   CLASS SERVERCONNECTION                                           =
# ======================================================================================================
class ServerConnection:
	def __init__(self, port, timeout=10):
		self.port = port
		self.timeout = forceInt(timeout)

	def createUnixSocket(self):
		logger.notice(u"Creating unix socket '%s'" % self.port)
		self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
		self._socket.settimeout(self.timeout)
		try:
			self._socket.connect(self.port)
		except Exception as exc:
			raise Exception(u"Failed to connect to socket '%s': %s" % (self.port, exc))

	def sendCommand(self, cmd):
		self.createUnixSocket()
		self._socket.send(forceUnicode(cmd).encode('utf-8'))
		result = None
		try:
			result = forceUnicode(self._socket.recv(4096))
		except Exception as exc:
			raise Exception(u"Failed to receive: %s" % exc)
		self._socket.close()
		if result.startswith(u'(ERROR)'):
			raise Exception(u"Command '%s' failed: %s" % (cmd, result))
		return result


class OpsiPXEConfdBackend(ConfigDataBackend):

	def __init__(self, **kwargs):
		ConfigDataBackend.__init__(self, **kwargs)

		self._name = 'opsipxeconfd'
		self._port = u'/var/run/opsipxeconfd/opsipxeconfd.socket'
		self._timeout = 10
		self._depotId = forceHostId(getfqdn(conf=OPSI_GLOBAL_CONF))
		self._opsiHostKey = None
		self._depotConnections = {}
		self._updateThreads = {}
		self._updateThreadsLock = threading.Lock()
		self._parseArguments(kwargs)

	def _parseArguments(self, kwargs):
		for (option, value) in kwargs.items():
			option = option.lower()
			if option == 'port':
				self._port = value
			elif option == 'timeout':
				self._timeout = forceInt(value)

	def _getDepotConnection(self, depotId):
		depotId = forceHostId(depotId)
		if depotId == self._depotId:
			return self

		if depotId not in self._depotConnections:
			if not self._opsiHostKey:
				depots = self._context.host_getObjects(id=self._depotId)
				if not depots or not depots[0].getOpsiHostKey():
					raise BackendMissingDataError(u"Failed to get opsi host key for depot '%s'" % self._depotId)
				self._opsiHostKey = depots[0].getOpsiHostKey()

			try:
				self._depotConnections[depotId] = JSONRPCBackend(
					address=u'https://%s:4447/rpc/backend/%s' % (depotId, self._name),
					username=self._depotId,
					password=self._opsiHostKey
				)
			except Exception as e:
				raise Exception(u"Failed to connect to depot '%s': %s" % (depotId, e))

		return self._depotConnections[depotId]

	def _getResponsibleDepotId(self, clientId):
		configStates = self._context.configState_getObjects(configId=u'clientconfig.depot.id', objectId=clientId)
		if configStates and configStates[0].values:
			depotId = configStates[0].values[0]
		else:
			configs = self._context.config_getObjects(id=u'clientconfig.depot.id')
			if not configs or not configs[0].defaultValues:
				raise Exception(u"Failed to get depotserver for client '%s', config 'clientconfig.depot.id' not set and no defaults found" % clientId)
			depotId = configs[0].defaultValues[0]
		return depotId

	def _pxeBootConfigurationUpdateNeeded(self, productOnClient):
		if productOnClient.productType != 'NetbootProduct':
			logger.debug(u"Not a netboot product: '%s', nothing to do" % productOnClient.productId)
			return False

		if not productOnClient.actionRequest:
			logger.debug(u"No action request update for product '%s', client '%s', nothing to do" % (productOnClient.productId, productOnClient.clientId))
			return False

		return True

	def _updateByProductOnClient(self, productOnClient):
		if not self._pxeBootConfigurationUpdateNeeded(productOnClient):
			return

		depotId = self._getResponsibleDepotId(productOnClient.clientId)
		if depotId != self._depotId:
			logger.info(u"Not responsible for client '%s', forwarding request to depot '%s'" % (productOnClient.clientId, depotId))
			return self._getDepotConnection(depotId).opsipxeconfd_updatePXEBootConfiguration(productOnClient.clientId)

		self.opsipxeconfd_updatePXEBootConfiguration(productOnClient.clientId)

	def opsipxeconfd_updatePXEBootConfiguration(self, clientId):
		clientId = forceHostId(clientId)
		self._updateThreadsLock.acquire()
		try:
			if not self._updateThreads.has_key(clientId):
				command = u'update %s' % clientId

				class UpdateThread(threading.Thread):
					def __init__(self, opsiPXEConfdBackend, clientId, command):
						threading.Thread.__init__(self)
						self._opsiPXEConfdBackend = opsiPXEConfdBackend
						self._clientId = clientId
						self._command = command
						self._updateEvent = threading.Event()
						self._delay = 3.0

					def run(self):
						while self._delay > 0:
							try:
								time.sleep(0.2)
							except:
								pass
							self._delay -= 0.2

						self._opsiPXEConfdBackend._updateThreadsLock.acquire()
						try:
							logger.info(u"Updating pxe boot configuration for client '%s'" % self._clientId)
							sc = ServerConnection(self._opsiPXEConfdBackend._port, self._opsiPXEConfdBackend._timeout)
							logger.info(u"Sending command '%s'" % self._command)
							result = sc.sendCommand(self._command)
							logger.info(u"Got result '%s'" % result)

						except Exception as e:
							logger.critical(u"Failed to update PXE boot configuration for client '%s': %s" % (self._clientId, e))

						del self._opsiPXEConfdBackend._updateThreads[self._clientId]
						self._opsiPXEConfdBackend._updateThreadsLock.release()

					def delay(self):
						self._delay = 3.0

				self._updateThreads[clientId] = UpdateThread(self, clientId, command)
				self._updateThreads[clientId].start()
			else:
				self._updateThreads[clientId].delay()
		finally:
			self._updateThreadsLock.release()

	def backend_exit(self):
		for connection in self._depotConnections.values():
			try:
				self._depotConnections.backend_exit()
			except:
				pass
		self._updateThreadsLock.acquire()
		for updateThread in self._updateThreads.values():
			updateThread.join(5)
		self._updateThreadsLock.release()

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   Hosts                                                                                     -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def host_updateObject(self, host):
		if not isinstance(host, OpsiClient):
			return

		if not host.ipAddress and not host.hardwareAddress:
			# Not of interest
			return

		self.opsipxeconfd_updatePXEBootConfiguration(host.id)

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductOnClients                                                                          -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productOnClient_insertObject(self, productOnClient):
		self._updateByProductOnClient(productOnClient)

	def productOnClient_updateObject(self, productOnClient):
		self._updateByProductOnClient(productOnClient)

	def productOnClient_deleteObjects(self, productOnClients):
		errors = []
		for productOnClient in productOnClients:
			try:
				self._updateByProductOnClient(productOnClient)
			except Exception as e:
				errors.append(forceUnicode(e))

		if errors:
			raise Exception(u', '.join(errors))

	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ConfigStates                                                                              -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def configState_insertObject(self, configState):
		if configState.configId != 'clientconfig.depot.id':
			return

		self.opsipxeconfd_updatePXEBootConfiguration(configState.objectId)

	def configState_updateObject(self, configState):
		if configState.configId != 'clientconfig.depot.id':
			return

		self.opsipxeconfd_updatePXEBootConfiguration(configState.objectId)

	def configState_deleteObjects(self, configStates):
		errors = []
		for configState in configStates:
			if configState.configId != 'clientconfig.depot.id':
				continue

			try:
				self.opsipxeconfd_updatePXEBootConfiguration(configState.objectId)
			except Exception as e:
				errors.append(forceUnicode(e))

		if errors:
			raise Exception(u', '.join(errors))
