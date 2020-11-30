# -*- coding: utf-8 -*-

# This file is part of python-opsi.
# Copyright (C) 2014-2019 uib GmbH <info@uib.de>

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
Configuration data for the backend.

.. versionadded:: 4.0.6.1

:author: Niko Wenselowski <n.wenselowski@uib.de>
:author: Erol Ueluekmen <e.ueluekmen@uib.de>
:license: GNU Affero General Public License version 3
"""
import codecs
import os
import re
from collections import namedtuple

import OPSI.Backend.BackendManager as bm
import OPSI.System.Posix as Posix
from OPSI.Object import UnicodeConfig, BoolConfig
from OPSI.Logger import Logger
from OPSI.Exceptions import BackendMissingDataError
from OPSI.Util.Task.Samba import SMB_CONF

LOGGER = Logger()

SimpleBoolConfig = namedtuple('SimpleBoolConfig', ['id', 'description', 'value'])
SimpleUnicodeConfig = namedtuple('SimpleUnicodeConfig', ['id', 'description', 'values'])


def initializeConfigs(backend=None, configServer=None, pathToSMBConf=SMB_CONF):
	"""
	Adding default configurations to the backend.

	:param backend: The backend to use. If this is ``None`` an backend \
will be created.
	:param configServer: The ConfigServer that should be used as \
default. Supply this if ``clientconfig.configserver.url`` or \
``clientconfig.depot.id`` are not yet set.
	:type configServer: OPSI.Object.OpsiConfigserver
	:param pathToSMBConf: The path the samba configuration.
	:type pathToSMBConf: str


	.. versionchanged:: 4.0.6.1

		Adding ``dynamic`` as value for ``clientconfig.depot.drive`` if missing.


	.. versionchanged:: 4.0.6.3

		Adding WAN extension configurations if missing.


	.. versionchanged:: 4.0.7.24

		On UCR we try read the domain for ``clientconfig.depot.user``
		preferably from Univention config registry (UCR).
	"""
	backendProvided = True

	if backend is None:
		backendProvided = False
		backend = bm.BackendManager()
		backend.backend_createBase()

	LOGGER.notice(u'Setting up default values.')
	backend.config_createObjects(getDefaultConfigs(backend, configServer, pathToSMBConf))  # pylint: disable=maybe-no-member

	addDynamicDepotDriveSelection(backend)
	createWANconfigs(backend)
	createInstallByShutdownConfig(backend)
	createUserProfileManagementDefaults(backend)

	LOGGER.notice(u'Finished setting up default values.')
	if not backendProvided:
		backend.backend_exit()


def getDefaultConfigs(backend, configServer=None, pathToSMBConf=SMB_CONF):
	configIdents = set(backend.config_getIdents(returnType='unicode'))  # pylint: disable=maybe-no-member

	if Posix.isUCS():
		# We have a domain present and people might want to change this.
		if u'clientconfig.depot.user' not in configIdents:
			LOGGER.debug("Missing clientconfig.depot.user - adding it.")

			depotuser = u'pcpatch'
			depotdomain = readWindowsDomainFromUCR()
			if not depotdomain:
				LOGGER.info(u"Reading domain from UCR returned no result. "
							u"Trying to read from samba config.")
				depotdomain = readWindowsDomainFromSambaConfig(pathToSMBConf)

			if depotdomain:
				depotuser = u'\\'.join((depotdomain, depotuser))

			LOGGER.debug(u"Using {0!r} as clientconfig.depot.user.", depotuser)

			yield UnicodeConfig(
				id=u'clientconfig.depot.user',
				description=u'User for depot share',
				possibleValues=[],
				defaultValues=[depotuser],
				editable=True,
				multiValue=False
			)

	if configServer and u'clientconfig.configserver.url' not in configIdents:
		LOGGER.debug("Missing clientconfig.configserver.url - adding it.")
		ipAddress = configServer.getIpAddress()
		if not ipAddress:
			raise BackendMissingDataError(
				"No IP address configured for the configserver {0}".format(
					configServer.id
				)
			)

		yield UnicodeConfig(
			id=u'clientconfig.configserver.url',
			description=u'URL(s) of opsi config service(s) to use',
			possibleValues=[u'https://%s:4447/rpc' % ipAddress],
			defaultValues=[u'https://%s:4447/rpc' % ipAddress],
			editable=True,
			multiValue=True
		)

	if configServer and u'clientconfig.depot.id' not in configIdents:
		LOGGER.debug(u"Missing clientconfig.depot.id - adding it.")
		yield UnicodeConfig(
			id=u'clientconfig.depot.id',
			description=u'ID of the opsi depot to use',
			possibleValues=[configServer.getId()],
			defaultValues=[configServer.getId()],
			editable=True,
			multiValue=False
		)

	if u'clientconfig.depot.dynamic' not in configIdents:
		LOGGER.debug(u"Missing clientconfig.depot.dynamic - adding it.")
		yield BoolConfig(
			id=u'clientconfig.depot.dynamic',
			description=u'Use dynamic depot selection',
			defaultValues=[False]
		)

	if u'clientconfig.depot.drive' not in configIdents:
		LOGGER.debug(u"Missing clientconfig.depot.drive - adding it.")

		yield UnicodeConfig(
			id=u'clientconfig.depot.drive',
			description=u'Drive letter for depot share',
			possibleValues=[
				u'a:', u'b:', u'c:', u'd:', u'e:', u'f:', u'g:', u'h:',
				u'i:', u'j:', u'k:', u'l:', u'm:', u'n:', u'o:', u'p:',
				u'q:', u'r:', u's:', u't:', u'u:', u'v:', u'w:', u'x:',
				u'y:', u'z:',
				u'dynamic'
			],
			defaultValues=[u'p:'],
			editable=False,
			multiValue=False
		)

	if u'clientconfig.depot.protocol' not in configIdents:
		LOGGER.debug(u"Missing clientconfig.depot.protocol - adding it.")
		yield UnicodeConfig(
			id=u'clientconfig.depot.protocol',
			description=u'Protocol for file transfer',
			possibleValues=['cifs', 'webdav'],
			defaultValues=['cifs'],
			editable=False,
			multiValue=False
		)

	if u'clientconfig.windows.domain' not in configIdents:
		LOGGER.debug(u"Missing clientconfig.windows.domain - adding it.")
		yield UnicodeConfig(
			id=u'clientconfig.windows.domain',
			description=u'Windows domain',
			possibleValues=[],
			defaultValues=[readWindowsDomainFromSambaConfig(pathToSMBConf)],
			editable=True,
			multiValue=False
		)

	if u'opsi-linux-bootimage.append' not in configIdents:
		LOGGER.debug(u"Missing opsi-linux-bootimage.append - adding it.")
		yield UnicodeConfig(
			id=u'opsi-linux-bootimage.append',
			description=u'Extra options to append to kernel command line',
			possibleValues=[
				u'acpi=off', u'irqpoll', u'noapic', u'pci=nomsi',
				u'vga=normal', u'reboot=b', u'mem=2G', u'nomodeset',
				u'ramdisk_size=2097152'
			],
			defaultValues=[u''],
			editable=True,
			multiValue=True
		)

	if u'license-management.use' not in configIdents:
		LOGGER.debug(u"Missing license-management.use - adding it.")
		yield BoolConfig(
			id=u'license-management.use',
			description=u'Activate license management',
			defaultValues=[False]
		)

	if u'software-on-demand.active' not in configIdents:
		LOGGER.debug(u"Missing software-on-demand.active - adding it.")
		yield BoolConfig(
			id=u'software-on-demand.active',
			description=u'Activate software-on-demand',
			defaultValues=[False]
		)

	if u'software-on-demand.product-group-ids' not in configIdents:
		LOGGER.debug(u"Missing software-on-demand.product-group-ids - adding it.")
		yield UnicodeConfig(
			id=u'software-on-demand.product-group-ids',
			description=(
				u'Product group ids containing products which are '
				u'allowed to be installed on demand'
			),
			possibleValues=[u'software-on-demand'],
			defaultValues=[u'software-on-demand'],
			editable=True,
			multiValue=True
		)

	if u'product_sort_algorithm' not in configIdents:
		LOGGER.debug(u"Missing product_sort_algorithm - adding it.")
		yield UnicodeConfig(
			id=u'product_sort_algorithm',
			description=u'Product sorting algorithm',
			possibleValues=[u'algorithm1', u'algorithm2'],
			defaultValues=[u'algorithm1'],
			editable=False,
			multiValue=False
		)

	if u'clientconfig.dhcpd.filename' not in configIdents:
		LOGGER.debug(u"Missing clientconfig.dhcpd.filename - adding it.")
		yield UnicodeConfig(
			id=u'clientconfig.dhcpd.filename',
			description=(
				u"The name of the file that will be presented to the "
				u"client on an TFTP request. For an client that should "
				u"boot via UEFI this must include the term 'elilo'."
			),
			possibleValues=[u'elilo'],
			defaultValues=[u''],
			editable=True,
			multiValue=False
		)


def readWindowsDomainFromSambaConfig(pathToConfig=SMB_CONF):
	"""
	Get the Windows domain (workgroup) from smb.conf.
	If no workgroup can be found this returns an empty string.

	:param pathToConfig: Path to the smb.conf
	:type pathToConfig: str
	:return: The Windows domain in uppercase letters.
	:rtype: str
	"""
	winDomain = u''
	if os.path.exists(pathToConfig):
		pattern = re.compile(r'^\s*workgroup\s*=\s*(\S+)\s*$')
		with codecs.open(pathToConfig, 'r', 'utf-8') as sambaConfig:
			for line in sambaConfig:
				match = pattern.search(line)
				if match:
					winDomain = match.group(1).upper()
					break

	return winDomain


def readWindowsDomainFromUCR():
	"""
	Get the Windows domain from Univention Config registry
	If no domain can be found this returns an empty string.

	:return: The Windows domain in uppercase letters.
	:rtype: str
	"""
	domain = ''
	try:
		readCommand = u'{ucr} get windows/domain'.format(ucr=Posix.which('ucr'))
		for output in Posix.execute(readCommand):
			if output:
				domain = output.strip().upper()
				break
	except Posix.CommandNotFoundException as missingCommandError:
		LOGGER.info('Could not find ucr: {0}', missingCommandError)

	return domain


def addDynamicDepotDriveSelection(backend):
	config = backend.config_getObjects(id=u'clientconfig.depot.drive')[0]

	if u'dynamic' not in config.possibleValues:
		LOGGER.debug(
				u"Could not find possibility to select dynamic drive "
				u"selection. Adding it to 'clientconfig.depot.drive'."
		)

		config.possibleValues.append(u'dynamic')
		backend.config_updateObject(config)


def createWANconfigs(backend):
	"Create the configurations that are used by the WAN extension if missing."

	configs = [
		SimpleBoolConfig(u"opsiclientd.event_gui_startup.active",
			u"gui_startup active", True),
		SimpleBoolConfig(u"opsiclientd.event_gui_startup{user_logged_in}.active",
			u"gui_startup{user_logged_in} active", True),
		SimpleBoolConfig(u"opsiclientd.event_net_connection.active",
			u"event_net_connection active", False),
		SimpleBoolConfig(u"opsiclientd.event_timer.active",
			u"event_timer active", False)
	]

	_createBooleanConfigsIfMissing(backend, configs)


def _createBooleanConfigsIfMissing(backend, configs):
	availableConfigs = set(backend.config_getIdents())
	for config in configs:
		if config.id not in availableConfigs:
			LOGGER.debug(u"Adding missing config {0!r}", config.id)
			backend.config_createBool(config.id, config.description, config.value)


def createInstallByShutdownConfig(backend):
	"Create the configurations that are used by the InstallByShutdown extension if missing."

	config = SimpleBoolConfig(u"clientconfig.install_by_shutdown.active",
		u"install_by_shutdown active", False)

	_createBooleanConfigsIfMissing(backend, [config])


def createUserProfileManagementDefaults(backend):
	"Create the default configuration for the User Profile Management extension."

	eventActiveConfig = SimpleBoolConfig(u"opsiclientd.event_user_login.active", u"user_login active", False)
	_createBooleanConfigsIfMissing(backend, [eventActiveConfig])

	actionProcressorCommand = SimpleUnicodeConfig(
		'opsiclientd.event_user_login.action_processor_command',
		"user_login action_processor",
		["%action_processor.command% /sessionid service_session /loginscripts /silent"]
	)

	if actionProcressorCommand.id not in set(backend.config_getIdents()):
		LOGGER.debug(u"Adding missing config {0!r}", actionProcressorCommand.id)
		backend.config_createUnicode(
			actionProcressorCommand.id,
			actionProcressorCommand.description,
			possibleValues=actionProcressorCommand.values,
			defaultValues=actionProcressorCommand.values
		)
