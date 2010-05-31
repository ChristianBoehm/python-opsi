#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = = = = = =
   =   opsi python library - HostControl     =
   = = = = = = = = = = = = = = = = = = = = = =
   
   This module is part of the desktop management solution opsi
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
   @author: Jan Schneider <j.schneider@uib.de>
   @license: GNU General Public License version 2
"""

__version__ = '3.5'

# Imports
import socket, threading, httplib, base64, time, struct

# OPSI imports
from OPSI.Logger import *
from OPSI.Types import *
from OPSI.Object import *
from OPSI.Backend.Backend import *
from OPSI.Util import fromJson, toJson, non_blocking_connect_https, KillableThread

# Get logger instance
logger = Logger()


# ======================================================================================================
# =                                      CLASS RPCTHREAD                                               =
# ======================================================================================================
class RpcThread(KillableThread):
	def __init__(self, hostControlBackend, hostId, address, username, password, method, params=[]):
		KillableThread.__init__(self)
		self.hostControlBackend = hostControlBackend
		self.hostId   = forceHostId(hostId)
		self.address  = forceIpAddress(address)
		self.username = forceUnicode(username)
		self.password = forceUnicode(password)
		self.method   = forceUnicode(method)
		self.params   = forceList(params)
		self.error    = None
		self.result   = None
		self.started  = 0
		self.ended    = 0
		
	def run(self):
		try:
			self.started = time.time()
			timeout = self.hostControlBackend._hostRpcTimeout - 5
			if (timeout < 0):
				timeout = 0
			
			query = toJson({ 'id': 1, 'method': self.method, 'params': self.params }).encode('utf-8')
			
			connection = httplib.HTTPSConnection(self.address, self.hostControlBackend._opsiclientdPort)
			non_blocking_connect_https(connection, timeout)
			connection.putrequest('POST', '/opsiclientd')
			connection.putheader('content-type', 'application/json-rpc')
			connection.putheader('content-length', str(len(query)))
			auth = u'%s:%s' % (self.username, self.password)
			connection.putheader('Authorization', 'Basic '+ base64.encodestring(auth.encode('latin-1')).strip())
			connection.endheaders()
			connection.send(query)
			
			response = connection.getresponse()
			response = response.read()
			response = fromJson(unicode(response, 'utf-8'))
			
			self.error  = response.get('error')
			self.result = response.get('result')
		except Exception, e:
			self.error = forceUnicode(e)
		self.ended = time.time()

# ======================================================================================================
# =                                  CLASS HOSTCONTROLBACKEND                                          =
# ======================================================================================================
class HostControlBackend(ExtendedBackend):
	
	def __init__(self, backend, **kwargs):
		self._name = 'hostcontrol'
		
		ExtendedBackend.__init__(self, backend, **kwargs)
		
		self._opsiclientdPort = 4441
		self._hostRpcTimeout  = 15
		self._resolveHostAddress = True
		self._maxConnections = 20
		
		# Parse arguments
		for (option, value) in kwargs.items():
			option = option.lower()
			if   option in ('opsiclientdport',):
				self._opsiclientdPort = forceInt(value)
			elif option in ('hostrpctimeout',):
				self._hostRpcTimeout = forceInt(value)
			elif option in ('resolvehostaddress',):
				self._resolveHostAddress = forceBool(value)
			elif option in ('maxconnections',):
				self._maxConnections = forceInt(value)
			
		if (self._maxConnections < 1):
			self._maxConnections = 1
		
	def _opsiclientdRpc(self, hostIds, method, params=[]):
		hostIds = forceHostIdList(hostIds)
		method  = forceUnicode(method)
		params  = forceList(params)
		
		errors = []
		rpcts = []
		for host in self._context.host_getObjects(id = hostIds):
			try:
				address = host.ipAddress
				if not address and self._resolveHostAddress:
					address = socket.gethostbyname(host.id)
				if not address:
					raise Exception(u"Failed to get ip address for host '%s'" % host.id)
				rpcts.append(
					RpcThread(
						hostControlBackend = self,
						hostId   = host.id,
						address  = address,
						username = host.id,
						password = host.opsiHostKey,
						method   = method,
						params   = params))
			except Exception, e:
				errors.append(forceUnicode(e))
		
		runningThreads = 0
		while rpcts:
			newRpcts = []
			for rpct in rpcts:
				if rpct.ended:
					if rpct.error:
						logger.error(u"Rpc to host %s failed, error: %s" % (rpct.hostId, rpct.error))
						errors.append(u"%s: %s" % (rpct.hostId, rpct.error))
					else:
						logger.info(u"Rpc to host %s successful, result: %s" % (rpct.hostId, rpct.result))
					runningThreads -= 1
					continue
				if not rpct.started:
					if (runningThreads < self._maxConnections):
						logger.debug(u"Starting rpc to host %s" % rpct.hostId)
						rpct.start()
						runningThreads += 1
				else:
					timeRunning = time.time() - rpct.started
					if (timeRunning >= self._hostRpcTimeout):
						logger.error(u"Rpc to host %s (address: %s) timed out after %0.2f seconds, terminating" % (rpct.hostId, rpct.address, timeRunning))
						errors.append(u"%s: timed out after %0.2f seconds" % (rpct.hostId, timeRunning))
						try:
							rpct.terminate()
						except Exception, e:
							logger.error(u"Failed to terminate rpc thread: %s" % e)
						runningThreads -= 1
						continue
				newRpcts.append(rpct)
			rpcts = newRpcts
			time.sleep(0.1)
		
		if errors:
			raise Exception(u', '.join(errors))
		
	def hostControl_start(self, hostIds=[]):
		''' Switches on remote computers using WOL. '''
		hostIds = forceHostIdList(hostIds)
		hosts = self._context.host_getObjects(attributes = ['hardwareAddress'], id = hostIds)
		errors = []
		for host in hosts:
			try:
				if not host.hardwareAddress:
					raise BackendMissingDataError(u"Failed to get hardware address for host '%s'" % host.id)
				
				mac = host.hardwareAddress.replace(':', '')
				
				# Pad the synchronization stream.
				data = ''.join(['FFFFFFFFFFFF', mac * 16])
				send_data = ''
				
				# Split up the hex values and pack.
				for i in range(0, len(data), 2):
					send_data = ''.join([
						send_data,
						struct.pack('B', int(data[i: i + 2], 16)) ])
				
				logger.debug(u"Sending data to network broadcast [%s]" % data)
				# Broadcast it to the LAN.
				sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
				sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
				sock.sendto(send_data, ('<broadcast>', 12287))
				sock.close()
			except Exception, e:
				errors.append(forceUnicode(e))
		if errors:
			raise Exception(u', '.join(errors))
	
	def hostControl_shutdown(self, hostIds=[]):
		hostIds = forceHostIdList(hostIds)
		return self._opsiclientdRpc(hostIds = hostIds, method = 'shutdown', params = [])
	
	def hostControl_fireEvent(self, event, hostIds=[]):
		event = forceUnicode(event)
		hostIds = forceHostIdList(hostIds)
		return self._opsiclientdRpc(hostIds = hostIds, method = 'fireEvent', params = [ event ])
		
	
	
	
	
	
	
	
	
	
	
	
	
	
	
	
	
	
	
