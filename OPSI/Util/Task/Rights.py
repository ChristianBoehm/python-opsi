# -*- coding: utf-8 -*-

# This module is part of the desktop management solution opsi
# (open pc server integration) http://www.opsi.org

# Copyright (C) 2014-2019 uib GmbH - http://www.uib.de/

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
Setting access rights for opsi.

Opsi needs different access rights and ownerships for files and folders
during its use. To ease the setting of these permissions this modules
provides helpers for this task.


.. versionadded:: 4.0.6.1


.. versionchanged:: 4.0.6.3

	Added function :py:func:`chown`.


.. versionchanged:: 4.0.6.4

	Improved :py:func:`removeDuplicatesFromDirectories`.


.. versionchanged:: 4.0.6.24

	Disabled :py:func:`removeDuplicatesFromDirectories` to avoid
	problems with wrong rights set on /var/lib/opsi/depot


.. versionchanged:: 4.0.7.9

	Many internal refactorings to make adding new directories easier.


:copyright:  uib GmbH <info@uib.de>
:author: Niko Wenselowski <n.wenselowski@uib.de>
:license: GNU Affero General Public License version 3
"""

import grp
import os
import pwd
import re
import stat
from collections import namedtuple

from OPSI.Config import (
	FILE_ADMIN_GROUP as _FILE_ADMIN_GROUP,
	OPSI_ADMIN_GROUP as _ADMIN_GROUP,
	DEFAULT_DEPOT_USER as _CLIENT_USER,
	OPSICONFD_USER as _OPSICONFD_USER)
from OPSI.Logger import Logger
from OPSI.Util import findFilesGenerator
from OPSI.System.Posix import (
	getLocalFqdn as getLocalFQDN, isCentOS, isDebian, isOpenSUSE, isRHEL, isSLES, isUbuntu,
	isUCS)

__all__ = ('setRights', 'setPasswdRights')

logger = Logger()

_HAS_ROOT_RIGHTS = os.geteuid() == 0
KNOWN_EXECUTABLES = frozenset((
	'create_driver_links.py', 'opsi-deploy-client-agent',
	'service_setup.sh', 'setup.py', 'show_drivers.py', 'winexe',
	'windows-image-detector.py',
))

Rights = namedtuple("Rights", ["uid", "gid", "files", "directories", "correctLinks"])


def setPasswdRights():
	"""
	Setting correct permissions on ``/etc/opsi/passwd``.
	"""
	targetFile = '/etc/opsi/passwd'
	logger.notice("Setting rights on %s", targetFile)
	opsiconfdUid = pwd.getpwnam(_OPSICONFD_USER)[2]
	adminGroupGid = grp.getgrnam(_ADMIN_GROUP)[2]
	os.chown(targetFile, opsiconfdUid, adminGroupGid)
	os.chmod(targetFile, 0o660)


def setRights(path='/'):
	logger.debug("Setting rights on %s", path)
	logger.debug("euid is %s", os.geteuid())

	dirAndRights = getDirectoriesAndExpectedRights()

	for startPath, rights in filterDirsAndRights(path, dirAndRights):
		if os.path.isfile(path):
			chown(path, rights.uid, rights.gid)
			setRightsOnFile(os.path.abspath(path), rights.files)
			continue
		
		if not os.path.exists(startPath):
			logger.warning("File not found '%s'", startPath)
			continue

		logger.notice("Setting rights on directory %s", startPath)
		logger.trace("Rights configuration: %s", rights)
		chown(startPath, rights.uid, rights.gid)
		os.chmod(startPath, rights.directories)
		for filepath in findFilesGenerator(startPath, prefix=startPath, returnLinks=rights.correctLinks, excludeFile=re.compile(r"(.swp|~)$")):
			st = os.stat(filepath)
			if (rights.uid != -1 and rights.uid != st.st_uid) or (rights.gid != -1 and rights.gid != st.st_gid):
				chown(filepath, rights.uid, rights.gid)
			
			if stat.S_ISDIR(st.st_mode):
				logger.debug("Setting rights on directory %s", filepath)
				mode = st.st_mode & 0o07777
				if mode != rights.directories:
					#logger.trace("%s: %o != %o", filepath, mode, rights.directories)
					os.chmod(filepath, rights.directories)
			elif stat.S_ISREG(st.st_mode):
				mode = st.st_mode & 0o07777
				if mode != rights.files:
					#logger.trace("%s: %o != %o", filepath, mode, rights.files)
					setRightsOnFile(filepath, rights.files)

		if startPath.startswith('/var/lib/opsi') and _HAS_ROOT_RIGHTS:
			clientUserUid = pwd.getpwnam(_CLIENT_USER)[2]
			fileAdminGroupGid = grp.getgrnam(_FILE_ADMIN_GROUP)[2]

			os.chmod('/var/lib/opsi', 0o750)
			chown('/var/lib/opsi', clientUserUid, fileAdminGroupGid)
			setRightsOnSSHDirectory(clientUserUid, fileAdminGroupGid)


def filterDirsAndRights(path, iterable):
	'''
	Iterates over `iterable` and the yields the appropriate directories.

	This function also avoids that directorires get returned more than once.
	'''
	basedir = getAbsoluteDir(path)

	processedDirectories = set()
	for dirname, right in iterable:
		if not dirname.startswith(basedir) and not basedir.startswith(dirname):
			logger.debug("Skipping %s", dirname)
			continue

		startPath = dirname
		if basedir.startswith(dirname):
			startPath = basedir

		if startPath in processedDirectories:
			logger.debug("Already proceesed %s, skipping.", startPath)
			continue

		yield startPath, right

		processedDirectories.add(startPath)


def getAbsoluteDir(path):
	'''
	Returns to absolute path to the directory.

	If `path` is no directory the absolute path to the dir containing
	`path` will be used.
	'''
	basedir = os.path.abspath(path)
	if not os.path.isdir(basedir):
		basedir = os.path.dirname(basedir)

	return basedir


def getDirectoriesAndExpectedRights():
	opsiconfdUid = pwd.getpwnam(_OPSICONFD_USER)[2]
	adminGroupGid = grp.getgrnam(_ADMIN_GROUP)[2]
	fileAdminGroupGid = grp.getgrnam(_FILE_ADMIN_GROUP)[2]

	yield '/etc/opsi', Rights(opsiconfdUid, adminGroupGid, 0o660, 0o770, True)
	yield '/var/log/opsi', Rights(opsiconfdUid, adminGroupGid, 0o660, 0o770, True)
	yield '/var/lib/opsi', Rights(opsiconfdUid, fileAdminGroupGid, 0o660, 0o770, False)

	dd = getDepotDirectories()
	yield dd["depot"], Rights(opsiconfdUid, fileAdminGroupGid, 0o660, 0o2770, False)
	yield dd["repository"], Rights(opsiconfdUid, fileAdminGroupGid, 0o660, 0o2770, False)
	yield dd["workbench"], Rights(-1, fileAdminGroupGid, 0o664, 0o2770, False)
	
	yield getPxeDirectory(), Rights(opsiconfdUid, fileAdminGroupGid, 0o664, 0o775, False)

	apacheDir = getWebserverRepositoryPath()
	if apacheDir:
		try:
			username, groupname = getWebserverUsernameAndGroupname()
			webUid = pwd.getpwnam(username)[2]
			webGid = grp.getgrnam(groupname)[2]

			yield apacheDir, Rights(webUid, webGid, 0o664, 0o775, False)
		except (KeyError, TypeError, RuntimeError) as kerr:
			logger.debug("Lookup of user / group failed: %s", kerr)

CACHED_DEPOT_DIRS = {}
def getDepotDirectories():
	global CACHED_DEPOT_DIRS
	if not CACHED_DEPOT_DIRS:
		CACHED_DEPOT_DIRS = {
			"depot": "/var/lib/opsi/depot",
			"repository": "/var/lib/opsi/repository",
			"workbench": "/var/lib/opsi/workbench"
		}
		try:
			from OPSI.Backend.BackendManager import BackendManager
			with BackendManager() as backend:
				depot = backend.host_getObjects(type='OpsiDepotserver', id=getLocalFQDN())[0]
				for name, url in (
					("depot", depot.getDepotLocalUrl()),
					("repository", depot.getRepositoryLocalUrl()),
					("workbench", depot.getWorkbenchLocalUrl())
				):
					if url.startswith('file:///'):
						CACHED_DEPOT_DIRS[name] = url[7:]
		except IndexError:
			logger.warning("Failed to get directories from depot: No depots found")
		except Exception as e:
			logger.warning("Failed to get directories from depot: %s", e)
	return CACHED_DEPOT_DIRS

def getPxeDirectory():
	if isSLES() or isOpenSUSE():
		return '/var/lib/tftpboot/opsi'
	else:
		return '/tftpboot/linux'

def getWebserverRepositoryPath():
	"""
	Returns the path to the directory where packages for Linux netboot \
installations may be.

	On an unsuported distribution or without the relevant folder
	existing `None` will be returned.
	"""
	if any(func() for func in (isDebian, isCentOS, isRHEL, isUbuntu)):
		path = '/var/www/html/opsi'
	elif isUCS():
		path = '/var/www/opsi'
	elif isOpenSUSE() or isSLES():
		path = '/srv/www/htdocs/opsi'
	else:
		logger.info("Unsupported distribution.")
		return

	if not os.path.exists(path):
		logger.debug("Found path %s but does not exist.", path)
		path = None

	return path

def getWebserverUsernameAndGroupname():
	'''
	Returns the name of the user and group belonging to the webserver \
in the default configuration.

	:raises RuntimeError: If running on an Unsupported distribution.
	'''
	if isDebian() or isUbuntu() or isUCS():
		return 'www-data', 'www-data'
	elif isOpenSUSE() or isSLES():
		return 'wwwrun', 'www'
	elif isCentOS() or isRHEL():
		return 'apache', 'apache'
	else:
		raise RuntimeError("Unsupported distribution.")


def setRightsOnFile(filepath, filemod):
	logger.debug("Setting rights on file %s", filepath)
	if filepath.startswith(getDepotDirectories()["depot"]):
		if os.path.basename(filepath) in KNOWN_EXECUTABLES:
			logger.debug("Setting rights on special file %s", filepath)
			os.chmod(filepath, 0o770)
		else:
			logger.debug("Setting rights on file %s", filepath)
			os.chmod(filepath, (os.stat(filepath)[0] | 0o660) & 0o770)
	else:
		logger.debug("Setting rights %s on file %s", filemod, filepath)
		os.chmod(filepath, filemod)


def chown(path, uid, gid):
	"""
	Set the ownership of a file or folder.

	The uid will only be set if the efficte uid is 0 - i.e. running with sudo.

	If changing the owner fails an Exception will only be risen if the
	current uid is 0 - we are root.
	In all other cases only a warning is shown.
	"""
	try:
		if _HAS_ROOT_RIGHTS:
			logger.debug("Setting ownership to %s:%s on %s", uid, gid, path)
			if os.path.islink(path):
				os.lchown(path, uid, gid)
			else:
				os.chown(path, uid, gid)
		else:
			logger.debug("Setting ownership to -1:%s on %s", gid, path)
			if os.path.islink(path):
				os.lchown(path, -1, gid)
			else:
				os.chown(path, -1, gid)
	except OSError as fist:
		if _HAS_ROOT_RIGHTS:
			# We are root so something must be really wrong!
			raise fist

		logger.warning("Failed to set ownership on %s: %s", path, fist)
		logger.notice("Please try setting the rights as root.")


def setRightsOnSSHDirectory(userId, groupId, path='/var/lib/opsi/.ssh'):
	if os.path.exists(path):
		os.chown(path, userId, groupId)
		os.chmod(path, 0o750)

		idRsa = os.path.join(path, 'id_rsa')
		if os.path.exists(idRsa):
			os.chmod(idRsa, 0o640)
			os.chown(idRsa, userId, groupId)

		idRsaPub = os.path.join(path, 'id_rsa.pub')
		if os.path.exists(idRsaPub):
			os.chmod(idRsaPub, 0o644)
			os.chown(idRsaPub, userId, groupId)

		authorizedKeys = os.path.join(path, 'authorized_keys')
		if os.path.exists(authorizedKeys):
			os.chmod(authorizedKeys, 0o600)
			os.chown(authorizedKeys, userId, groupId)
