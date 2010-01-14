#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = = = = = =
   =   opsi python library - OpsiPXEConfd    =
   = = = = = = = = = = = = = = = = = = = = = =
   
   This module is part of the desktop management solution opsi
   (open pc server integration) http://www.opsi.org
   
   Copyright (C) 2006, 2007, 2008 uib GmbH
   
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
   @author: Jan Schneider <j.schneider@uib.de>
   @license: GNU General Public License version 2
"""

__version__ = '3.5'

# Imports
import socket

# OPSI imports
from OPSI.Logger import *
from OPSI.Types import *
from OPSI.Object import *
from OPSI.Backend.Backend import *

# Get logger instance
logger = Logger()


# ======================================================================================================
# =                                   CLASS SERVERCONNECTION                                           =
# ======================================================================================================
class ServerConnection:
	def __init__(self, port):
		self.port = port
	
	def createUnixSocket(self):
		logger.notice(u"Creating unix socket '%s'" % self.port)
		self._socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
		self._socket.settimeout(5.0)
		try:
			self._socket.connect(self.port)
		except Exception, e:
			raise Exception(u"Failed to connect to socket '%s': %s" % (self.port, e))
	
	def sendCommand(self, cmd):
		self.createUnixSocket()
		self._socket.send( forceUnicode(cmd).encode('utf-8') )
		result = None
		try:
			result = forceUnicode(self._socket.recv(4096))
		except Exception, e:
			raise Exception(u"Failed to receive: %s" % e)
		self._socket.close()
		if result.startswith(u'(ERROR)'):
			raise Exception(u"Command '%s' failed: %s" % (cmd, result))
	
# ======================================================================================================
# =                                 CLASS OPSIPXECONFDBACKEND                                          =
# ======================================================================================================
class OpsiPXEConfdBackend(DataBackend):
	
	def __init__(self, username = '', password = '', address = 'localhost', **kwargs):
		DataBackend.__init__(self, username, password, address, **kwargs)
		self.__port = u'/var/run/opsipxeconfd/opsipxeconfd.socket'
	
	def _writePXEBootConfiguration(self, productState):
		if not productState.actionRequest:
			logger.debug(u"No action request set for product '%s', host '%s', nothing to do" % (productState.productId, productState.hostId))
			return
		product = self.product_getObjects(attributes = ['type'], productId = productState.productId)[0]
		if not isinstance(product, NetbootProduct):
			logger.debug(u"Not a netboot product: '%s', nothing to do" % product.id)
			return
		host = self.host_getObjects(attributes = ['ipAddress', 'hardwareAddress'], hostId = productState.hostId)[0]
		
		logger.info(u"Setting pxe boot configuration for host '%s', product '%s'" % (host.id, product.id))
		
		command = u''
		if (productState.actionRequest == 'none'):
			command = u'unset %s' % host.id
		else:
			command = u'set %s productId=%s' % (host.id, product.id)
		
		try:
			sc = ServerConnection(self.__port)
			logger.info(u"Sending command '%s'" % command)
			result = sc.sendCommand(command)
			logger.info(u"Got result '%s'" % result)
		except Exception, e:
			raise BackendIOError(u"Failed to write PXE boot configuration: %s" % e)
	
	def backend_exit(self):
		pass
	
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	# -   ProductStates                                                                             -
	# - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	def productState_insertObject(self, productState):
		self._writePXEBootConfiguration(productState)
	
	def productState_updateObject(self, productState):
		self._writePXEBootConfiguration(productState)
	
	def productState_getObjects(self, attributes=[], **filter):
		return
	
	def productState_deleteObjects(self, productStates):
		return
	
	
	
	
	
	
	
	
	
	
	
	
	
	
	
	
	
