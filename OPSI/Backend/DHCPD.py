# -*- coding: utf-8 -*-

# This file is part of python-opsi.
# Copyright (C) 2010-2019 uib GmbH <info@uib.de>

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
DHCPD Backend.

This backend works edits the configuration of the DHCPD and restarts
the daemon afterwards.

:license: GNU Affero General Public License version 3
"""

import os
import sys
import time
import fcntl
import socket
import threading
from functools import lru_cache
from contextlib import contextmanager

import OPSI.System as System
from OPSI.Backend.Base import ConfigDataBackend
from OPSI.Backend.JSONRPC import JSONRPCBackend
from OPSI.Exceptions import (
	BackendIOError, BackendBadValueError, BackendMissingDataError,
	BackendUnableToConnectError, BackendUnaccomplishableError)
from OPSI.Logger import Logger
from OPSI.Object import OpsiClient, Host
from OPSI.Types import forceBool, forceDict, forceHostId, forceObjectClass
from OPSI.Util.File import DHCPDConfFile
from OPSI.Util import getfqdn

__all__ = ('DHCPDBackend', )

logger = Logger()

WAIT_AFTER_RELOAD = 4.0

@contextmanager
def dhcpd_lock(lock_type=""):
	lock_file = '/var/lock/opsi-dhcpd-lock'
	with open(lock_file, 'a+') as lock_fh:
		try:
			os.chmod(lock_file, 0o666)
		except PermissionError:
			pass
		attempt = 0
		while True:
			attempt += 1
			try:
				fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
				break
			except IOError:
				if attempt > 200:
					raise
				time.sleep(0.1)
		lock_fh.seek(0)
		lines = lock_fh.readlines()
		if len(lines) >= 100:
			lines = lines[-100:]
		lines.append(f"{time.time()};{os.path.basename(sys.argv[0])};{os.getpid()};{lock_type}\n")
		lock_fh.seek(0)
		lock_fh.truncate()
		lock_fh.writelines(lines)
		lock_fh.flush()
		yield None
		if lock_type == "config_reload":
			time.sleep(WAIT_AFTER_RELOAD)
		fcntl.flock(lock_fh, fcntl.LOCK_UN)
	#os.remove(lock_file)

class DHCPDBackend(ConfigDataBackend):  # pylint: disable=too-many-instance-attributes

	def __init__(self, **kwargs):
		self._name = 'dhcpd'

		ConfigDataBackend.__init__(self, **kwargs)
		self._dhcpdConfigFile = System.Posix.locateDHCPDConfig('/etc/dhcp3/dhcpd.conf')
		self._reloadConfigCommand = None
		self._fixedAddressFormat = 'IP'
		self._defaultClientParameters = {
			'next-server': socket.gethostbyname(getfqdn()),
			'filename': 'linux/pxelinux.0'
		}
		self._dhcpdOnDepot = False

		# Parse arguments
		for (option, value) in kwargs.items():
			option = option.lower()
			if option == 'dhcpdconfigfile':
				self._dhcpdConfigFile = value
			elif option == 'reloadconfigcommand':
				self._reloadConfigCommand = value
			elif option == 'defaultclientparameters':
				self._defaultClientParameters = forceDict(value)
			elif option == 'fixedaddressformat':
				if value not in ('IP', 'FQDN'):
					raise BackendBadValueError("Bad value '%s' for fixedAddressFormat, possible values are %s" % (value, ', '.join(('IP', 'FQDN'))))
				self._fixedAddressFormat = value
			elif option == 'dhcpdondepot':
				self._dhcpdOnDepot = forceBool(value)

		if self._defaultClientParameters.get('next-server') and self._defaultClientParameters['next-server'].startswith('127'):
			raise BackendBadValueError("Refusing to use ip address '%s' as default next-server" % self._defaultClientParameters['next-server'])

		self._dhcpdConfFile = DHCPDConfFile(self._dhcpdConfigFile)
		self._reloadThread = None
		self._depotId = forceHostId(getfqdn())
		self._opsiHostKey = None
		self._depotConnections = {}

	def _startReloadThread(self):
		class ReloadThread(threading.Thread):
			def __init__(self, reloadConfigCommand):
				threading.Thread.__init__(self)
				self._reloadConfigCommand = reloadConfigCommand
				self._reloadEvent = threading.Event()
				self._isReloading = False
				if not self._reloadConfigCommand:
					self._reloadConfigCommand = '/usr/bin/sudo {command}'.format(
						command=System.Posix.getDHCPDRestartCommand(default='/etc/init.d/dhcp3-server restart')
					)

			@property
			def isBusy(self):
				return self._isReloading or self._reloadEvent.isSet()

			def triggerReload(self):
				logger.debug("Reload triggered")
				if not self._reloadEvent.isSet():
					self._reloadEvent.set()

			def run(self):
				while True:
					if self._reloadEvent.wait(WAIT_AFTER_RELOAD):
						with dhcpd_lock("config_reload"):
							self._isReloading = True
							self._reloadEvent.clear()
							try:
								logger.notice("Reloading dhcpd config using command: '%s'", self._reloadConfigCommand)
								result = System.execute(self._reloadConfigCommand)
								for line in result:
									if 'error' in line:
										raise RuntimeError('\n'.join(result))
							except Exception as err:# pylint: disable=broad-except
								logger.critical("Failed to reload dhcpd config: %s", err)
							self._isReloading = False

		self._reloadThread = ReloadThread(self._reloadConfigCommand)
		self._reloadThread.daemon = True
		self._reloadThread.start()

	def _triggerReload(self):
		if not self._reloadThread:
			self._startReloadThread()
		self._reloadThread.triggerReload()

	def _getDepotConnection(self, depotId):
		depotId = forceHostId(depotId)
		if depotId == self._depotId:
			return self

		try:
			return self._depotConnections[depotId]
		except KeyError as err:
			if not self._opsiHostKey:
				depots = self._context.host_getObjects(id=self._depotId)  # pylint: disable=maybe-no-member
				if not depots or not depots[0].getOpsiHostKey():
					raise BackendMissingDataError(
						f"Failed to get opsi host key for depot '{self._depotId}'"
					) from err
				self._opsiHostKey = depots[0].getOpsiHostKey()

			try:
				self._depotConnections[depotId] = JSONRPCBackend(
					address=f'https://{depotId}:4447/rpc/backend/dhcpd',
					username=self._depotId,
					password=self._opsiHostKey
				)
			except Exception as err:
				raise BackendUnableToConnectError(
					f"Failed to connect to depot '{depotId}': {err}"
				) from err

			return self._depotConnections[depotId]

	def _getResponsibleDepotId(self, clientId):
		configStates = self._context.configState_getObjects(configId='clientconfig.depot.id', objectId=clientId)  # pylint: disable=maybe-no-member
		try:
			depotId = configStates[0].values[0]
		except IndexError as err:
			configs = self._context.config_getObjects(id='clientconfig.depot.id')  # pylint: disable=maybe-no-member
			if not configs or not configs[0].defaultValues:
				raise BackendUnaccomplishableError(
					f"Failed to get depotserver for client '{clientId}', config 'clientconfig.depot.id' not set and no defaults found"
				) from err
			depotId = configs[0].defaultValues[0]

		return depotId

	def backend_exit(self):
		if self._reloadThread:
			logger.info("Waiting for reload thread")
			for _i in range(10):
				if self._reloadThread.isBusy:
					time.sleep(1)

	def _dhcpd_updateHost(self, host):
		host = forceObjectClass(host, Host)

		if self._dhcpdOnDepot:
			depotId = self._getResponsibleDepotId(host.id)  # pylint: disable=maybe-no-member
			if depotId != self._depotId:
				logger.info("Not responsible for client '%s', forwarding request to depot '%s'", host.id, depotId)  # pylint: disable=maybe-no-member
				return self._getDepotConnection(depotId).dhcpd_updateHost(host)  # pylint: disable=maybe-no-member
		return self.dhcpd_updateHost(host)

	def dhcpd_updateHost(self, host):  # pylint: disable=too-many-branches
		host = forceObjectClass(host, Host)

		if not host.hardwareAddress:  # pylint: disable=maybe-no-member
			logger.warning("Cannot update dhcpd configuration for client %s: hardware address unknown", host)
			return

		hostname = _getHostname(host.id)  # pylint: disable=maybe-no-member

		ipAddress = host.ipAddress  # pylint: disable=maybe-no-member
		if not ipAddress:
			try:
				logger.info("Ip addess of client %s unknown, trying to get host by name", host)
				ipAddress = socket.gethostbyname(host.id)  # pylint: disable=maybe-no-member
				logger.info("Client fqdn resolved to %s", ipAddress)
			except Exception as err:  # pylint: disable=broad-except
				logger.debug("Failed to get IP by hostname: %s", err)
				with dhcpd_lock("config_read"):
					self._dhcpdConfFile.parse()
					currentHostParams = self._dhcpdConfFile.getHost(hostname)

				if currentHostParams:
					logger.debug(
						'Trying to use address for %s from existing DHCP '
						'configuration.', hostname
					)

					if currentHostParams.get('fixed-address'):
						ipAddress = currentHostParams['fixed-address']
					else:
						raise BackendIOError(
							f"Cannot update dhcpd configuration for client {host.id}: "
							"ip address unknown and failed to get ip address from DHCP configuration file."
						) from err
				else:
					raise BackendIOError(
						f"Cannot update dhcpd configuration for client {host.id}: "
						"ip address unknown and failed to get host by name"
					) from err

		fixedAddress = ipAddress
		if self._fixedAddressFormat == 'FQDN':
			fixedAddress = host.id  # pylint: disable=maybe-no-member

		parameters = forceDict(self._defaultClientParameters)
		if not self._dhcpdOnDepot:
			try:
				depot = self._context.host_getObjects(id=self._getResponsibleDepotId(host.id))[0]  # pylint: disable=maybe-no-member
				if depot.ipAddress:
					parameters['next-server'] = depot.ipAddress
			except Exception as err:  # pylint: disable=broad-except
				logger.error("Failed to get depot info: %s", err)

		with dhcpd_lock("config_update"):
			try:
				self._dhcpdConfFile.parse()
				currentHostParams = self._dhcpdConfFile.getHost(hostname)
				if currentHostParams and (currentHostParams.get('hardware', ' ').split(' ')[1] == host.hardwareAddress) \
					and (currentHostParams.get('fixed-address') == fixedAddress) \
					and (currentHostParams.get('next-server') == parameters.get('next-server')):

					logger.debug("DHCPD config of host '%s' unchanged, no need to update config file", host)
					return

				self._dhcpdConfFile.addHost(
					hostname=hostname,
					hardwareAddress=host.hardwareAddress,  # pylint: disable=maybe-no-member
					ipAddress=ipAddress,
					fixedAddress=fixedAddress,
					parameters=parameters
				)
				self._dhcpdConfFile.generate()
			except Exception as err:  # pylint: disable=broad-except
				logger.error(err, exc_info=True)

		self._triggerReload()

	def _dhcpd_deleteHost(self, host):
		host = forceObjectClass(host, Host)
		if self._dhcpdOnDepot:
			for depot in self._context.host_getObjects(id=self._depotId):  # pylint: disable=maybe-no-member
				if depot.id != self._depotId:
					self._getDepotConnection(depot.id).dhcpd_deleteHost(host)  # pylint: disable=maybe-no-member
		self.dhcpd_deleteHost(host)

	def dhcpd_deleteHost(self, host):
		host = forceObjectClass(host, Host)

		with dhcpd_lock("config_update"):
			try:
				self._dhcpdConfFile.parse()
				hostname = _getHostname(host.id)
				if not self._dhcpdConfFile.getHost(hostname):  # pylint: disable=maybe-no-member
					return
				self._dhcpdConfFile.deleteHost(hostname)  # pylint: disable=maybe-no-member
				self._dhcpdConfFile.generate()
			except Exception as err:  # pylint: disable=broad-except
				logger.error(err, exc_info=True)

		self._triggerReload()

	def host_insertObject(self, host):
		if not isinstance(host, OpsiClient):
			return

		logger.debug("Inserting host: %s", host)
		self._dhcpd_updateHost(host)

	def host_updateObject(self, host):
		if not isinstance(host, OpsiClient):
			return

		if not host.ipAddress and not host.hardwareAddress:
			# Not of interest
			return

		logger.debug("Updating host: %s", host)
		try:
			self._dhcpd_updateHost(host)
		except Exception as err:  # pylint: disable=broad-except
			logger.error(err, exc_info=True)

	def host_deleteObjects(self, hosts):
		logger.debug("Deleting host: %s", hosts)

		errors = []
		for host in hosts:
			if not isinstance(host, OpsiClient):
				continue

			try:
				self._dhcpd_deleteHost(host)
			except Exception as err:  # pylint: disable=broad-except
				errors.append(str(err))

		if errors:
			raise RuntimeError(', '.join(errors))

	def configState_insertObject(self, configState):
		if configState.configId != 'clientconfig.depot.id':
			return

		for host in self._context.host_getObjects(id=configState.objectId):
			self.host_updateObject(host)

	def configState_updateObject(self, configState):
		if configState.configId != 'clientconfig.depot.id':
			return

		for host in self._context.host_getObjects(id=configState.objectId):
			self.host_updateObject(host)

	def configState_deleteObjects(self, configStates):
		for configState in configStates:
			if configState.configId != 'clientconfig.depot.id':
				continue

			for host in self._context.host_getObjects(id=configState.objectId):
				self.host_updateObject(host)


@lru_cache(maxsize=256)
def _getHostname(fqdn):
	"""
	Return only the hostname of an FQDN.

	:param fqdn: The FQDN to work with.
	:type fqdn: str
	:rtype: str
	"""
	return fqdn.split('.')[0]
