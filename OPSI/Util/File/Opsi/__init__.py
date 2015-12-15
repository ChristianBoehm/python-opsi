#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
opsi python library - File.Opsi

This module is part of the desktop management solution opsi
(open pc server integration) http://www.opsi.org

Copyright (C) 2006-2015 uib GmbH

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

:copyright: uib GmbH <info@uib.de>
:author: Jan Schneider <j.schneider@uib.de>
:author: Niko Wenselowski <n.wenselowski@uib.de>
:license: GNU General Public License version 2
"""

import bz2
import collections
import datetime
import gzip
import os
import re
import tarfile
import tempfile
import shutil
import socket
import StringIO
from contextlib import closing
from hashlib import sha1
from subprocess import Popen, PIPE, STDOUT

if os.name == 'posix':
	import fcntl
	import grp
	import pwd
	from OPSI.System.Posix import SysInfo
elif os.name == 'nt':
	import win32con
	import win32file
	import pywintypes

import OPSI.System
from OPSI.Logger import Logger
from OPSI.Object import BoolProductProperty, LocalbootProduct, NetbootProduct, Product, ProductDependency, ProductProperty, UnicodeProductProperty
from OPSI.Types import (BackendBadValueError, OpsiBackupBackendNotFound,
	OpsiBackupFileError, OpsiBackupFileNotFound, forceActionRequest, forceBool,
	forceDictList, forceFilename, forceHostId, forceInstallationStatus,
	forceInt, forceList, forceObjectClass, forceObjectClassList,
	forceOpsiHostKey, forcePackageVersion, forceProductId,
	forceProductPriority, forceProductPropertyType, forceProductType,
	forceProductVersion, forceRequirementType, forceUnicode, forceUnicodeList,
	forceUnicodeLower)
from OPSI.Util.File import ConfigFile, IniFile, TextFile, requiresParsing
from OPSI.Util import md5sum, toJson, fromJson

__version__ = '4.0.6.39'

logger = Logger()


class HostKeyFile(ConfigFile):

	lineRegex = re.compile('^\s*([^:]+)\s*:\s*([0-9a-fA-F]{32})\s*$')

	def __init__(self, filename, lockFailTimeout=2000):
		ConfigFile.__init__(self, filename, lockFailTimeout, commentChars=[';', '/', '#'])
		self._opsiHostKeys = {}

	def parse(self, lines=None):
		if lines:
			self._lines = forceUnicodeList(lines)
		else:
			self.readlines()
		self._parsed = False
		for line in ConfigFile.parse(self):
			match = self.lineRegex.search(line)
			if not match:
				logger.error(u"Found bad formatted line '%s' in pckey file '%s'" % (line, self._filename))
				continue
			try:
				hostId = forceHostId(match.group(1))
				opsiHostKey = forceOpsiHostKey(match.group(2))
				if hostId in self._opsiHostKeys:
					logger.error(u"Found duplicate host '%s' in pckey file '%s'" % (hostId, self._filename))
				self._opsiHostKeys[hostId] = opsiHostKey
			except BackendBadValueError as error:
				logger.error(u"Found bad formatted line '%s' in pckey file '%s': %s" % (line, self._filename, error))
		self._parsed = True
		return self._opsiHostKeys

	def generate(self):
		self._lines = [u'{0}:{1}'.format(hostId, self._opsiHostKeys[hostId])
			for hostId in sorted(self._opsiHostKeys.keys())]

		self.open('w')
		self.writelines()
		self.close()

	@requiresParsing
	def getOpsiHostKey(self, hostId):
		hostId = forceHostId(hostId)
		if hostId not in self._opsiHostKeys:
			return None
		return self._opsiHostKeys[hostId]

	@requiresParsing
	def setOpsiHostKey(self, hostId, opsiHostKey):
		hostId = forceHostId(hostId)
		opsiHostKey = forceOpsiHostKey(opsiHostKey)
		self._opsiHostKeys[hostId] = opsiHostKey

	@requiresParsing
	def deleteOpsiHostKey(self, hostId):
		hostId = forceHostId(hostId)
		if hostId in self._opsiHostKeys:
			del self._opsiHostKeys[hostId]


class BackendACLFile(ConfigFile):

	aclEntryRegex = re.compile('^([^:]+)+\s*:\s*(\S.*)$')

	def __init__(self, filename, lockFailTimeout=2000):
		ConfigFile.__init__(self, filename, lockFailTimeout, commentChars=['#'])

	def parse(self, lines=None):
		if lines:
			self._lines = forceUnicodeList(lines)
		else:
			self.readlines()
		self._parsed = False
		# acl example:
		#    <method>: <aclType>[(aclTypeParam[(aclTypeParamValue,...)];...)]
		#    xyz_.*:   opsi_depotserver(attributes(id,name))
		#    abc:      self(attributes(!opsiHostKey));sys_group(admin, group 2, attributes(!opsiHostKey))

		acl = []
		for line in ConfigFile.parse(self):
			match = re.search(self.aclEntryRegex, line)
			if not match:
				raise Exception(u"Found bad formatted line '%s' in acl file '%s'" % (line, self._filename))
			method = match.group(1).strip()
			acl.append([method, []])
			for entry in match.group(2).split(';'):
				entry = entry.strip()
				aclType = entry
				aclTypeParams = ''
				if entry.find('(') != -1:
					(aclType, aclTypeParams) = entry.split('(', 1)
					if aclTypeParams[-1] != ')':
						raise Exception(u"Bad formatted acl entry '%s': trailing ')' missing" % entry)
					aclType = aclType.strip()
					aclTypeParams = aclTypeParams[:-1]

				if aclType not in ('all', 'self', 'opsi_depotserver', 'opsi_client', 'sys_group', 'sys_user'):
					raise Exception(u"Unhandled acl type: '%s'" % aclType)
				entry = {'type': aclType, 'allowAttributes': [], 'denyAttributes': [], 'ids': []}
				if not aclTypeParams:
					if aclType in ('sys_group', 'sys_user'):
						raise Exception(u"Bad formatted acl type '%s': no params given" % aclType)
				else:
					aclTypeParam = u''
					aclTypeParamValues = [u'']
					inAclTypeParamValues = False
					for i in range(len(aclTypeParams)):
						c = aclTypeParams[i]
						if c == '(':
							if inAclTypeParamValues:
								raise Exception(u"Bad formatted acl type params '%s'" % aclTypeParams)
							inAclTypeParamValues = True
						elif c == ')':
							if not inAclTypeParamValues or not aclTypeParam:
								raise Exception(u"Bad formatted acl type params '%s'" % aclTypeParams)
							inAclTypeParamValues = False
						elif c != ',' or i == len(aclTypeParams) - 1:
							if inAclTypeParamValues:
								aclTypeParamValues[-1] += c
							else:
								aclTypeParam += c

						if c == ',' or i == len(aclTypeParams) - 1:
							if inAclTypeParamValues:
								if i == len(aclTypeParams) - 1:
									raise Exception(u"Bad formatted acl type params '%s'" % aclTypeParams)
								aclTypeParamValues.append(u'')
							else:
								aclTypeParam = aclTypeParam.strip()
								tmp = []
								for t in aclTypeParamValues:
									t = t.strip()
									if not t:
										continue
									tmp.append(t)
								aclTypeParamValues = tmp
								if aclTypeParam == 'attributes':
									for v in aclTypeParamValues:
										if not v:
											continue
										if v.startswith('!'):
											entry['denyAttributes'].append(v[1:].strip())
										else:
											entry['allowAttributes'].append(v)
								elif aclType in ('sys_group', 'sys_user', 'opsi_depotserver', 'opsi_client'):
									entry['ids'].append(aclTypeParam.strip())
								else:
									raise Exception(u"Unhandled acl type param '%s' for acl type '%s'" % (aclTypeParam, aclType))
								aclTypeParam = u''
								aclTypeParamValues = [u'']

				acl[-1][1].append(entry)
		self._parsed = True
		return acl


class BackendDispatchConfigFile(ConfigFile):
	DISPATCH_ENTRY_REGEX = re.compile('^([^:]+)+\s*:\s*(\S.*)$')

	def parse(self, lines=None):
		"""
		Returns the dispatch config entries with RegEx and corresponding backends.

		:returntype: [['regex', ['backend1', 'backend2',]]]
		"""
		if lines:
			self._lines = forceUnicodeList(lines)
		else:
			self.readlines()

		self._parsed = False
		dispatch = []
		for line in ConfigFile.parse(self, lines):
			match = self.DISPATCH_ENTRY_REGEX.search(line)
			if not match:
				logger.error(u"Found bad formatted line '%s' in dispatch config file '%s'" % (line, self._filename))
				continue

			method = match.group(1).strip()
			backends = [entry.strip() for entry
						in match.group(2).strip(',').split(',')]
			dispatch.append([method, backends])
		self._parsed = True

		return dispatch

	def getUsedBackends(self, lines=None):
		"""
		Returns the backends used by the dispatch configuration.
		This will not include any information on where it is used.

		:returntype: set(['backend1', 'backend2'])
		"""
		collectedBackends = set()

		dispatchConfig = self.parse(lines=lines)
		for (_, backends) in dispatchConfig:
			collectedBackends.update(backends)

		return collectedBackends


class PackageContentFile(TextFile):
	def __init__(self, filename, lockFailTimeout=2000):
		TextFile.__init__(self, filename, lockFailTimeout)
		self._parsed = False
		self._productClientDataDir = u'/'
		self._clientDataFiles = []
		self._productServerDataDir = u'/'
		self._serverDataFiles = []

	def getClientDataFiles(self):
		return self._clientDataFiles

	def setClientDataFiles(self, clientDataFiles):
		self._clientDataFiles = forceUnicodeList(clientDataFiles)

	def getServerDataFiles(self):
		return self._serverDataFiles

	def setServerDataFiles(self, serverDataFiles):
		self._serverDataFiles = forceUnicodeList(serverDataFiles)

	def setProductClientDataDir(self, productClientDataDir):
		self._productClientDataDir = forceFilename(productClientDataDir)

	def parse(self, lines=None):
		if lines:
			self._lines = forceUnicodeList(lines)
		else:
			self.readlines()

		fileInfo = {}
		for line in self._lines:
			(type, tmp) = line.strip().split(None, 1)
			filename = u''
			for i in range(len(tmp)):
				if tmp[i] == u"'":
					if i > 0:
						if tmp[i-1] == u'\\':
							filename = filename[:-1] + u"'"
							continue
						else:
							break
					else:
						continue
				filename += tmp[i]
			(size, target, md5) = (0, u'', '')
			tmp = tmp[i+2:]
			if u' ' in tmp:
				parts = tmp.split(None, 1)
				tmp = u''
				size = parts[0]
				if len(parts) > 1:
					tmp = parts[1]
			if type == 'f':
				md5 = tmp
			elif type == 'l':
				target = tmp[1:-1].replace(u'\\\'', u'\'')
			fileInfo[filename] = {'type': type, 'size': int(size), 'md5sum': md5, 'target': target}
		self._parsed = True
		return fileInfo

	def generate(self):
		self._lines = []
		for filename in self._clientDataFiles:
			try:
				#if (filename == self.clientDataDir):
				#	continue
				type = u'f'
				md5 = u''
				target = u''
				size = 0
				path = os.path.join(self._productClientDataDir, filename)
				if os.path.islink(path):
					type = u'l'
					target = os.path.realpath(path)
					if target.startswith(self._productClientDataDir):
						target = target[len(self._productClientDataDir):]
					else:
						if os.path.isdir(path):
							type = u'd'
						else:
							# link target not in client data dir => treat as file
							type = u'f'
							size = os.path.getsize(target)
							md5 = md5sum(target)
							target = u''
				elif os.path.isdir(path):
					type = u'd'
				else:
					size = os.path.getsize(path)
					md5 = md5sum(path)

				if target:
					self._lines.append("%s '%s' %s '%s'" % (type, filename.replace(u'\'', u'\\\''), size, target.replace(u'\'', u'\\\'')))
				else:
					self._lines.append("%s '%s' %s %s" % (type, filename.replace(u'\'', u'\\\''), size, md5))
			except Exception as error:
				logger.logException(error)

		self.open('w')
		self.writelines()
		self.close()


class PackageControlFile(TextFile):

	sectionRegex = re.compile('^\s*\[([^\]]+)\]\s*$')
	valueContinuationRegex = re.compile('^\s(.*)$')
	optionRegex = re.compile('^([^\:]+)\s*\:\s*(.*)$')

	def __init__(self, filename, lockFailTimeout=2000, opsi3compatible=False):
		TextFile.__init__(self, filename, lockFailTimeout)
		self._parsed = False
		self._sections = {}
		self._product = None
		self._productDependencies = []
		self._productProperties = []
		self._packageDependencies = []
		self._incrementalPackage = False
		self._opsi3compatible = forceBool(opsi3compatible)

	def parse(self, lines=None):
		if lines:
			self._lines = forceUnicodeList(lines)
		else:
			self.readlines()

		self._parsed = False
		self._sections = {}
		self._product = None
		self._productDependencies = []
		self._productProperties = []
		self._packageDependencies = []
		self._incrementalPackage = False

		sectionType = None
		option = None
		lineNum = 0
		for line in self._lines:
			lineNum += 1

			if line and line.startswith((';', '#')):
				# Comment
				continue

			line = line.replace('\r', '')

			match = self.sectionRegex.search(line)
			if match:
				sectionType = match.group(1).strip().lower()
				if sectionType not in ('package', 'product', 'windows', 'productdependency', 'productproperty', 'changelog'):
					raise Exception(u"Parse error in line %s: unknown section '%s'" % (lineNum, sectionType))
				if sectionType == 'changelog':
					self._sections[sectionType] = u''
				else:
					if sectionType in self._sections:
						self._sections[sectionType].append({})
					else:
						self._sections[sectionType] = [{}]
				continue

			elif not sectionType and line:
				raise Exception(u"Parse error in line %s: not in a section" % lineNum)

			if sectionType == 'changelog':
				if self._sections[sectionType]:
					self._sections[sectionType] += u'\n'
				self._sections[sectionType] += line.rstrip()
				continue

			key = None
			value = None
			match = self.valueContinuationRegex.search(line)
			if match:
				value = match.group(1)
			else:
				match = self.optionRegex.search(line)
				if match:
					key = match.group(1).lower()
					#value = match.group(2).lstrip()
					value = match.group(2).strip()

			if sectionType == 'package' and key in ('version', 'depends', 'incremental'):
				option = key
				if key == 'version':
					value = forceUnicodeLower(value)
				elif key == 'depends':
					value = forceUnicodeLower(value)
				elif key == 'incremental':
					value = forceBool(value)

			elif (sectionType == 'product' and key in \
					('id', 'type', 'name', 'description', 'advice',
					 'version', 'packageversion', 'priority',
					 'licenserequired', 'productclasses', 'pxeconfigtemplate',
					 'setupscript', 'uninstallscript', 'updatescript',
					 'alwaysscript', 'oncescript', 'customscript', 'userloginscript')):
				option = key
				if key == 'id':
					value = forceProductId(value)
				elif key == 'type':
					value = forceProductType(value)
				elif key == 'name':
					value = forceUnicode(value)
				elif key == 'description':
					value = forceUnicode(value)
				elif key == 'advice':
					value = forceUnicode(value)
				elif key == 'version':
					value = forceProductVersion(value)
				elif key == 'packageversion':
					value = forcePackageVersion(value)
				elif key == 'priority':
					value = forceProductPriority(value)
				elif key == 'licenserequired':
					value = forceBool(value)
				elif key == 'productclasses':
					value = forceUnicodeLower(value)
				elif key == 'pxeconfigtemplate':
					value = forceFilename(value)
				elif key == 'setupscript':
					value = forceFilename(value)
				elif key == 'uninstallscript':
					value = forceFilename(value)
				elif key == 'updatescript':
					value = forceFilename(value)
				elif key == 'alwaysscript':
					value = forceFilename(value)
				elif key == 'oncescript':
					value = forceFilename(value)
				elif key == 'customscript':
					value = forceFilename(value)
				elif key == 'userloginscript':
					value = forceFilename(value)

			elif sectionType == 'windows' and key in ('softwareids', ):
				option = key
				value = forceUnicodeLower(value)

			elif (sectionType == 'productdependency' and key in \
					('action', 'requiredproduct', 'requiredproductversion', 'requiredpackageversion',
					 'requiredclass', 'requiredstatus', 'requiredaction', 'requirementtype')):
				option = key
				if key == 'action':
					value = forceActionRequest(value)
				elif key == 'requiredproduct':
					value = forceProductId(value)
				elif key == 'requiredproductversion':
					value = forceProductVersion(value)
				elif key == 'requiredpackageversion':
					value = forcePackageVersion(value)
				elif key == 'requiredclass':
					value = forceUnicodeLower(value)
				elif key == 'requiredstatus':
					value = forceInstallationStatus(value)
				elif key == 'requiredaction':
					value = forceActionRequest(value)
				elif key == 'requirementtype':
					value = forceRequirementType(value)

			elif sectionType == 'productproperty' and key in ('type', 'name', 'default', 'values', 'description', 'editable', 'multivalue'):
				option = key
				if key == 'type':
					value = forceProductPropertyType(value)
				elif key == 'name':
					value = forceUnicodeLower(value)
				elif key == 'default':
					value = forceUnicode(value)
				elif key == 'values':
					value = forceUnicode(value)
				elif key == 'description':
					value = forceUnicode(value)
				elif key == 'editable':
					value = forceBool(value)
				elif key == 'multivalue':
					value = forceBool(value)

			else:
				value = forceUnicode(line)

			if not option:
				raise Exception(u"Parse error in line '%s': no option / bad option defined" % lineNum)

			if not self._sections[sectionType][-1].has_key(option):
				self._sections[sectionType][-1][option] = value
			else:
				if isinstance(self._sections[sectionType][-1][option], unicode):
					if not self._sections[sectionType][-1][option].endswith('\n'):
						self._sections[sectionType][-1][option] += u'\n'
					self._sections[sectionType][-1][option] += value.lstrip()

		for (sectionType, secs) in self._sections.items():
			if sectionType == 'changelog':
				continue
			for i in range(len(secs)):
				for (option, value) in secs[i].items():
					if (sectionType == 'product' and option == 'productclasses') or \
					   (sectionType == 'package' and option == 'depends') or \
					   (sectionType == 'productproperty' and option == 'default') or \
					   (sectionType == 'productproperty' and option == 'values') or \
					   (sectionType == 'windows' and option == 'softwareids'):
						try:
							if not value.strip().startswith('{') and not value.strip().startswith('['):
								raise Exception(u'Not trying to read json string because value does not start with { or [')
							value = fromJson(value.strip())
							# Remove duplicates
							# TODO: use set
							tmp = []
							for v in forceList(value):
								if v not in tmp:
									tmp.append(v)
							value = tmp
						except Exception as error:
							logger.debug2(u"Failed to read json string '%s': %s" % (value.strip(), error))
							value = value.replace(u'\n', u'')
							value = value.replace(u'\t', u'')
							if not (sectionType == 'productproperty' and option == 'default'):
								value = value.split(u',')
								newV = []
								for v in value:
									v = v.strip()
									newV.append(v)
								value = newV
							# Remove duplicates
							# TODO: use set
							tmp = []
							for v in forceList(value):
								if v not in ('', None) and v not in tmp:
									tmp.append(v)
							value = tmp

					if isinstance(value, unicode):
						value = value.rstrip()

					self._sections[sectionType][i][option] = value

		if not self._sections.get('product'):
			raise Exception(u"Error in control file '%s': 'product' section not found" % self._filename)

		# Get package info
		for (option, value) in self._sections.get('package', [{}])[0].items():
			if option == 'depends':
				for dep in value:
					match = re.search('^\s*([^\(]+)\s*\(*\s*([^\)]*)\s*\)*', dep)
					if not match.group(1):
						raise Exception(u"Bad package dependency '%s' in control file" % dep)

					package = match.group(1).strip()
					version = match.group(2)
					condition = None
					if version:
						match = re.search('^\s*([<>]?=?)\s*([\w\.]+-*[\w\.]*)\s*$', version)
						if not match:
							raise Exception(u"Bad version string '%s' in package dependency" % version)

						condition = match.group(1)
						if not condition:
							condition = u'='
						if condition not in (u'=', u'<', u'<=', u'>', u'>='):
							raise Exception(u"Bad condition string '%s' in package dependency" % condition)
						version = match.group(2)
					else:
						version = None
					self._packageDependencies.append({'package': package, 'condition': condition, 'version': version})
			elif option == 'incremental':
				self._incrementalPackage = forceBool(value)

		# Create Product object
		product = self._sections['product'][0]
		Class = None
		if product.get('type') == 'NetbootProduct':
			Class = NetbootProduct
		elif product.get('type') == 'LocalbootProduct':
			Class = LocalbootProduct
		else:
			raise Exception(u"Error in control file '%s': unknown product type '%s'" % (self._filename, product.get('type')))

		self._product = Class(
			id=product.get('id'),
			name=product.get('name'),
			productVersion=product.get('version'),
			packageVersion=self._sections.get('package', [{}])[0].get('version') or product.get('packageversion'),
			licenseRequired=product.get('licenserequired'),
			setupScript=product.get('setupscript'),
			uninstallScript=product.get('uninstallscript'),
			updateScript=product.get('updatescript'),
			alwaysScript=product.get('alwaysscript'),
			onceScript=product.get('oncescript'),
			customScript=product.get('customscript'),
			priority=product.get('priority'),
			description=product.get('description'),
			advice=product.get('advice'),
			productClassIds=product.get('productclasses'),
			windowsSoftwareIds=self._sections.get('windows', [{}])[0].get('softwareids', []),
			changelog=self._sections.get('changelog')
		)
		if isinstance(self._product, NetbootProduct) and product.get('pxeconfigtemplate') is not None:
			self._product.setPxeConfigTemplate(product.get('pxeconfigtemplate'))

		if isinstance(self._product, LocalbootProduct) and product.get('userloginscript') is not None:
			self._product.setUserLoginScript(product.get('userloginscript'))
		self._product.setDefaults()

		# Create ProductDependency objects
		for productDependency in self._sections.get('productdependency', []):
			self._productDependencies.append(
				ProductDependency(
					productId=self._product.getId(),
					productVersion=self._product.getProductVersion(),
					packageVersion=self._product.getPackageVersion(),
					productAction=productDependency.get('action'),
					requiredProductId=productDependency.get('requiredproduct'),
					requiredProductVersion=productDependency.get('requiredproductversion'),
					requiredPackageVersion=productDependency.get('requiredpackageversion'),
					requiredAction=productDependency.get('requiredaction'),
					requiredInstallationStatus=productDependency.get('requiredstatus'),
					requirementType=productDependency.get('requirementtype')
				)
			)
			self._productDependencies[-1].setDefaults()

		# Create ProductProperty objects
		for productProperty in self._sections.get('productproperty', []):
			Class = UnicodeProductProperty

			if productProperty.get('type', '').lower() in ('unicodeproductproperty', 'unicode', ''):
				Class = UnicodeProductProperty
			elif productProperty.get('type', '').lower() in ('boolproductproperty', 'bool'):
				Class = BoolProductProperty
			else:
				raise Exception(u"Error in control file '%s': unknown product property type '%s'" % (self._filename, productProperty.get('type')))
			self._productProperties.append(
				Class(
					productId=self._product.getId(),
					productVersion=self._product.getProductVersion(),
					packageVersion=self._product.getPackageVersion(),
					propertyId=productProperty.get('name', u''),
					description=productProperty.get('description', u''),
					defaultValues=productProperty.get('default', [])
				)
			)
			if isinstance(self._productProperties[-1], UnicodeProductProperty):
				if productProperty.get('values') is not None:
					self._productProperties[-1].setPossibleValues(productProperty.get('values'))
				else:
					self._productProperties[-1].possibleValues = []

				if productProperty.get('editable') is not None:
					self._productProperties[-1].setEditable(productProperty['editable'])
				else:
					if not productProperty.get('values') in (None, []):
						self._productProperties[-1].setEditable(False)
					else:
						self._productProperties[-1].setEditable(True)

				if productProperty.get('multivalue') is not None:
					self._productProperties[-1].setMultiValue(productProperty['multivalue'])

			self._productProperties[-1].setDefaults()
		self._parsed = True
		return self._sections

	@requiresParsing
	def getProduct(self):
		return self._product

	def setProduct(self, product):
		self._product = forceObjectClass(product, Product)

	@requiresParsing
	def getProductDependencies(self):
		return self._productDependencies

	def setProductDependencies(self, productDependencies):
		self._productDependencies = forceObjectClassList(productDependencies, ProductDependency)

	@requiresParsing
	def getProductProperties(self):
		return self._productProperties

	def setProductProperties(self, productProperties):
		self._productProperties = forceObjectClassList(productProperties, ProductProperty)

	@requiresParsing
	def getPackageDependencies(self):
		return self._packageDependencies

	def setPackageDependencies(self, packageDependencies):
		self._packageDependencies = []
		for packageDependency in forceDictList(packageDependencies):
			if not packageDependency.get('package'):
				raise ValueError(u"No package given: %s" % packageDependency)
			if packageDependency.get('version') in (None, ''):
				packageDependency['version'] = None
				packageDependency['condition'] = None
			else:
				if not packageDependency.get('condition'):
					packageDependency['condition'] = u'='
				if not packageDependency['condition'] in (u'=', u'<', u'<=', u'>', u'>='):
					raise Exception(u"Bad condition string '%s' in package dependency" % packageDependency['condition'])
			self._packageDependencies.append(packageDependency)

	@requiresParsing
	def getIncrementalPackage(self):
		return self._incrementalPackage

	def setIncrementalPackage(self, incremental):
		self._incrementalPackage = forceBool(incremental)

	def generate(self):
		if not self._product:
			raise Exception(u"Got no data to write")

		logger.info(u"Writing opsi package control file '%s'" % self._filename)

		self._lines = [u'[Package]']
		self._lines.append(u'version: %s' % self._product.getPackageVersion())
		depends = u''
		for packageDependency in self._packageDependencies:
			if depends: depends += u', '
			depends += packageDependency['package']
			if packageDependency['version']:
				depends += u' (%s %s)' % (packageDependency['condition'], packageDependency['version'])

		self._lines.append(u'depends: %s' % depends)
		self._lines.append(u'incremental: %s' % self._incrementalPackage)
		self._lines.append(u'')

		self._lines.append(u'[Product]')
		productType = self._product.getType()
		if productType == 'LocalbootProduct':
			productType = 'localboot'
		elif productType == 'NetbootProduct':
			productType = 'netboot'
		else:
			raise Exception(u"Unhandled product type '%s'" % productType)

		self._lines.append(u'type: %s' % productType)
		self._lines.append(u'id: %s' % self._product.getId())
		self._lines.append(u'name: %s' % self._product.getName())
		self._lines.append(u'description: ')
		descLines = self._product.getDescription().split(u'\n')
		if len(descLines) > 0:
			self._lines[-1] += descLines[0]
			if len(descLines) > 1:
				for l in descLines[1:]:
					self._lines.append(u' %s' % l)
		self._lines.append(u'advice: %s' % self._product.getAdvice())
		self._lines.append(u'version: %s' % self._product.getProductVersion())
		self._lines.append(u'priority: %s' % self._product.getPriority())
		self._lines.append(u'licenseRequired: %s' % self._product.getLicenseRequired())
		if self._product.getProductClassIds() is not None:
			self._lines.append(u'productClasses: %s'  % u', '.join(self._product.getProductClassIds()))
		self._lines.append(u'setupScript: %s' % self._product.getSetupScript())
		self._lines.append(u'uninstallScript: %s' % self._product.getUninstallScript())
		self._lines.append(u'updateScript: %s' % self._product.getUpdateScript())
		self._lines.append(u'alwaysScript: %s' % self._product.getAlwaysScript())
		self._lines.append(u'onceScript: %s' % self._product.getOnceScript())
		if not self._opsi3compatible:
			self._lines.append(u'customScript: %s' % self._product.getCustomScript())
			if isinstance(self._product, LocalbootProduct):
				self._lines.append(u'userLoginScript: %s' % self._product.getUserLoginScript())
		if isinstance(self._product, NetbootProduct):
			pxeConfigTemplate = self._product.getPxeConfigTemplate()
			if not pxeConfigTemplate:
				pxeConfigTemplate = u''
			self._lines.append(u'pxeConfigTemplate: %s' % pxeConfigTemplate)
		self._lines.append(u'')

		if self._product.getWindowsSoftwareIds():
			self._lines.append('[Windows]')
			self._lines.append(u'softwareIds: %s' % u', '.join(self._product.getWindowsSoftwareIds()))
			self._lines.append(u'')

		for dependency in self._productDependencies:
			self._lines.append(u'[ProductDependency]')
			self._lines.append(u'action: %s' % dependency.getProductAction())
			if dependency.getRequiredProductId():
				self._lines.append(u'requiredProduct: %s' % dependency.getRequiredProductId())
			#if dependency.requiredProductClassId:
			#	self._lines.append( u'requiredClass: %s'   % dependency.requiredProductClassId )
			if not self._opsi3compatible and dependency.getRequiredProductVersion():
				self._lines.append(u'requiredProductVersion: %s' % dependency.getRequiredProductVersion())
			if not self._opsi3compatible and dependency.getRequiredPackageVersion():
				self._lines.append(u'requiredPackageVersion: %s' % dependency.getRequiredPackageVersion())
			if dependency.getRequiredAction():
				self._lines.append(u'requiredAction: %s' % dependency.getRequiredAction())
			if dependency.getRequiredInstallationStatus():
				self._lines.append(u'requiredStatus: %s' % dependency.getRequiredInstallationStatus())
			if dependency.getRequirementType():
				self._lines.append(u'requirementType: %s' % dependency.getRequirementType())
			self._lines.append(u'')

		for productProperty in self._productProperties:
			self._lines.append(u'[ProductProperty]')
			productPropertyType = 'unicode'
			if isinstance(productProperty, BoolProductProperty):
				productPropertyType = 'bool'
			if not self._opsi3compatible:
				self._lines.append(u'type: %s' % productPropertyType)
			self._lines.append(u'name: %s' % productProperty.getPropertyId())
			if not self._opsi3compatible and not isinstance(productProperty, BoolProductProperty):
				self._lines.append(u'multivalue: %s' % productProperty.getMultiValue())
				self._lines.append(u'editable: %s' % productProperty.getEditable())
			if productProperty.getDescription():
				self._lines.append(u'description: ')
				descLines = productProperty.getDescription().split(u'\n')
				if len(descLines) > 0:
					self._lines[-1] += descLines[0]
					if len(descLines) > 1:
						for l in descLines[1:]:
							self._lines.append(u' %s' % l)
			if self._opsi3compatible:
				if productProperty.getPossibleValues() and not productProperty.getEditable():
					self._lines.append(u'values: %s' % u', '.join(forceUnicodeList(productProperty.getPossibleValues())))
				if productProperty.getDefaultValues():
					self._lines.append(u'default: %s' % u', '.join(forceUnicodeList(productProperty.getDefaultValues())))
			else:
				if not isinstance(productProperty, BoolProductProperty) and productProperty.getPossibleValues():
					self._lines.append(u'values: %s' % toJson(productProperty.getPossibleValues()))
				if productProperty.getDefaultValues():
					if isinstance(productProperty, BoolProductProperty):
						self._lines.append(u'default: %s' % productProperty.getDefaultValues()[0])
					else:
						self._lines.append(u'default: %s' % toJson(productProperty.getDefaultValues()))
			self._lines.append(u'')

		if not self._opsi3compatible and self._product.getChangelog():
			self._lines.append(u'[Changelog]')
			self._lines.extend(self._product.getChangelog().split('\n'))
			self._lines.append(u'')

		self.open('w')
		self.writelines()
		self.close()


class OpsiConfFile(IniFile):

	sectionRegex = re.compile('^\s*\[([^\]]+)\]\s*$')
	optionRegex = re.compile('^([^\:]+)\s*\=\s*(.*)$')

	def __init__(self, filename=u'/etc/opsi/opsi.conf', lockFailTimeout=2000):
		ConfigFile.__init__(self, filename, lockFailTimeout, commentChars=[';', '#'])
		self._parsed = False
		self._sections = False
		self._opsiGroups = {}

	def parse(self, lines=None):
		if lines:
			self._lines = forceUnicodeList(lines)
		else:
			self.readlines()
		self.parsed = False
		self._sections = {}
		self._opsiConfig = {}

		sectionType = None
		lineNum = 0

		for line in self._lines:
			lineNum += 1
			line = line.strip()
			if line and line.startswith((';', '#')):
				# This is a comment
				continue

			line = line.replace('\r', '')

			match = self.sectionRegex.search(line)
			if match:
				sectionType = match.group(1).strip().lower()
				if sectionType not in ('groups', 'packages'):
					raise ValueError(u"Parse error in line %s: unknown section '%s'" % (lineNum, sectionType))
			elif not sectionType and line:
				raise ValueError(u"Parse error in line %s: not in a section" % lineNum)

			key = None
			value = None

			match = self.optionRegex.search(line)
			if match:
				key = match.group(1).strip().lower()
				value = match.group(2).strip()

			if sectionType == "groups":
				if key == "fileadmingroup":
					value = forceUnicodeLower(value)
				elif value:
					value = forceUnicodeList(
						[part.strip().lower() for part in value.split(",")]
					)

				if "groups" not in self._opsiConfig:
					self._opsiConfig["groups"] = {}

				if key and value:
					self._opsiConfig["groups"][key] = value
			elif sectionType == 'packages':
				if 'packages' not in self._opsiConfig:
					self._opsiConfig['packages'] = {}

				if key == 'use_pigz':
					self._opsiConfig['packages'][key] = forceBool(value)

		self._parsed = True
		return self._opsiConfig

	@requiresParsing
	def getOpsiFileAdminGroup(self):
		if not self._opsiConfig.get("groups", {}).get("fileadmingroup", ""):
			return "pcpatch"
		else:
			return self._opsiConfig["groups"]["fileadmingroup"]

	@requiresParsing
	def getOpsiGroups(self, groupType):
		if not self._opsiConfig.get("groups", {}).get(groupType, ""):
			return None
		else:
			return self._opsiConfig["groups"][groupType]

	@requiresParsing
	def isPigzEnabled(self):
		"""
		Check if the usage of pigz is enabled.

		:return: False if the usage of pigz is disabled, True otherwise.
		:returntype: bool
		"""
		if "packages" in self._opsiConfig and "use_pigz" in self._opsiConfig["packages"]:
			return self._opsiConfig["packages"]["use_pigz"]
		else:
			return True


class OpsiBackupArchive(tarfile.TarFile):

	CONTENT_DIR = "CONTENT"
	CONTROL_DIR = "CONTROL"

	CONF_DIR = "/etc/opsi"
	BACKEND_CONF_DIR = os.path.join(CONF_DIR, "backends")
	DISPATCH_CONF = os.path.join(CONF_DIR, "backendManager", "dispatch.conf")

	def __init__(self, name=None, mode=None, tempdir=tempfile.gettempdir(), fileobj=None, **kwargs):
		self.tempdir = tempdir
		self.mode = mode
		self.sysinfo = None
		compression = None

		if mode and ":" in mode:
			self.mode, compression = mode.split(":")
			assert compression in ("gz", "bz2")

		if name is None:
			self.sysinfo = self._probeSysInfo()
			name = self._generateNewArchive(suffix=compression)
			self.mode = 'w'
		elif not os.path.exists(name):
			if self.mode and not self.mode.startswith("w"):
				raise OpsiBackupFileNotFound("Cannot read from nonexisting file.")
		else:
			if self.mode and self.mode.startswith("w"):
				raise OpsiBackupFileError("Backup files are immutable.")

		if compression and not fileobj:
			if compression == "gz":
				fileobj = gzip.GzipFile(name, self.mode)
			if compression == "bz2":
				fileobj = bz2.BZ2File(name, self.mode)

		self._filemap = {}

		assert self.mode and str(self.mode)[0] in ("r", "w")
		tarfile.TarFile.__init__(self, name, self.mode, fileobj=fileobj, **kwargs)

		if self.mode.startswith("w"):
			if self.sysinfo is None:
				self.sysinfo = self._probeSysInfo()
		else:
			self.sysinfo = self._readSysInfo()
			self._filemap = self._readChecksumFile()

		try:
			self._backends = self._readBackendConfiguration()
		except OpsiBackupFileError as error:
			if self.mode.startswith("w"):
				raise error
			self._backends = None

	def _readBackendConfiguration(self):
		if os.path.exists(self.CONF_DIR) and os.path.exists(self.DISPATCH_CONF):
			try:
				dispatchedBackends = BackendDispatchConfigFile(self.DISPATCH_CONF).getUsedBackends()
			except Exception as error:
				logger.warning(u"Could not read dispatch configuration: %s" % forceUnicode(error))
				dispatchedBackends = []

		if not os.path.exists(self.BACKEND_CONF_DIR):
			raise OpsiBackupFileError(
				u'Could not read backend configuration: '
				u'Missing directory "{0}"'.format(self.BACKEND_CONF_DIR)
			)

		backends = {}
		for entry in os.listdir(self.BACKEND_CONF_DIR):
			if entry.endswith(".conf"):
				name = entry.split(".")[0].lower()
				if name in backends:
					raise OpsiBackupFileError("Multiple backends with the same name are not supported.")

				backendLocals = {'socket': socket, 'config': {}, 'module': ''}
				backendFile = os.path.join(self.BACKEND_CONF_DIR, entry)
				try:
					execfile(backendFile, backendLocals)
					backends[name] = {
						"name": name,
						"config": backendLocals["config"],
						"module": backendLocals['module'],
						"dispatch": (name in dispatchedBackends)
					}
				except Exception as error:
					logger.warning(u'Failed to read backend config "{filename}": {error}'.format(filename=forceFilename(entry), error=error))

		return backends


	def _getBackends(self, type=None):
		if not self._backends:
			self._backends = self._readBackendConfiguration()

		for backend in self._backends.values():
			if type is None or backend["module"].lower() == type:
				yield backend

	def _generateNewArchive(self, suffix=None):
		return os.path.join(self.tempdir, self._generateArchiveName(suffix=suffix))

	def _generateArchiveName(self, suffix=None):
		t = datetime.datetime.now()
		name = "%s_%s_%s.tar" % (self.sysinfo['hostname'], self.sysinfo['opsiVersion'], str(t).replace(" ", "_").replace(":", "-"))
		if suffix:
			name += ".%s" % suffix
		return name

	@staticmethod
	def _probeSysInfo():
		sysinfo = SysInfo()
		sysInfoDict = {}
		sysInfoDict["hostname"] = sysinfo.hostname
		sysInfoDict["fqdn"] = sysinfo.fqdn
		sysInfoDict["domainname"] = sysinfo.domainname
		sysInfoDict["distribution"] = sysinfo.distribution
		sysInfoDict["sysVersion"] = sysinfo.sysVersion
		sysInfoDict["distributionId"] = sysinfo.distributionId
		sysInfoDict["opsiVersion"] = sysinfo.opsiVersion
		return sysInfoDict

	def _readSysInfo(self):
		map = {}
		with closing(self.extractfile("%s/sysinfo" % self.CONTROL_DIR)) as fp:
			for line in fp.readlines():
				key, value = line.split(":")
				map[key.strip()] = value.strip()

		return map

	def _readChecksumFile(self):
		map = {}
		with closing(self.extractfile("%s/checksums" % self.CONTROL_DIR)) as fp:
			for line in fp.readlines():
				key, value = line.split(" ", 1)
				map[value.strip()] = key.strip()

		return map

	def _addContent(self, path, sub=()):
		dest = path
		if sub:
			dest = dest.replace(sub[0], sub[1])
		dest = os.path.join(self.CONTENT_DIR, dest)
		if os.path.isdir(path):
			self.add(path, dest, recursive=False)
			for entry in os.listdir(path):
				self._addContent(os.path.join(path, entry), sub=sub)
		else:
			checksum = sha1()

			with open(path) as f:
				chunk = True
				while chunk:
					chunk = f.read()
					checksum.update(chunk)

			self._filemap[dest] = checksum.hexdigest()

			self.add(path, dest)

	def _addChecksumFile(self):
		string = StringIO.StringIO()
		for path, checksum in self._filemap.iteritems():
			string.write("%s %s\n" % (checksum, path))
		string.seek(0)
		info = tarfile.TarInfo(name="%s/checksums" % self.CONTROL_DIR)
		info.size = len(string.buf)

		self.addfile(info, string)

	def _addSysInfoFile(self):
		string = StringIO.StringIO()

		for key, value in self.sysinfo.iteritems():
			string.write("%s: %s\n" %(key, value))
		string.seek(0)
		info = tarfile.TarInfo(name="%s/sysinfo" % self.CONTROL_DIR)
		info.size = len(string.buf)

		self.addfile(info, string)

	def verify(self):
		if self.mode.startswith("w"):
			raise OpsiBackupFileError("Backup archive is not finalized.")

		for member in self.getmembers():
			if member.isfile() and member.name.startswith(self.CONTENT_DIR):

				checksum = self._filemap[member.name]
				filesum = sha1()

				count = 0
				chunk = True
				with closing(self.extractfile(member)) as fp:
					while chunk:
						chunk = fp.read()
						count += len(chunk)
						filesum.update(chunk)

				if checksum != filesum.hexdigest():
					logger.debug2("Read %s bytes from file %s, resulting in checksum %s" % (count, member.name, filesum.hexdigest()))
					raise OpsiBackupFileError("Backup Archive is not valid: File %s is corrupetd" % member.name)

		return True

	def close(self):
		if self.mode.startswith("w"):
			self._addChecksumFile()
			self._addSysInfoFile()
		tarfile.TarFile.close(self)
		if self.fileobj and self._extfileobj:
			self.fileobj.close()

	def _extractFile(self, member, dest):
		tf, path = tempfile.mkstemp(dir=self.tempdir)

		try:
			checksum = self._filemap[member.name]
			filesum = sha1()

			chunk = True
			with closing(self.extractfile(member.name)) as fp:
				while chunk:
					chunk = fp.read()
					filesum.update(chunk)
					os.write(tf, chunk)

			if filesum.hexdigest() != checksum:
				raise OpsiBackupFileError("Error restoring file %s: checksum missmacht.")

			shutil.copyfile(path, dest)
			os.chown(dest, pwd.getpwnam(member.uname)[2], grp.getgrnam(member.gname)[2])
			os.chmod(dest, member.mode)
			os.utime(dest, (member.mtime, member.mtime))

		finally:
			os.close(tf)
			os.remove(path)

	def backupConfiguration(self):
		self._addContent(self.CONF_DIR, sub=(self.CONF_DIR, "CONF"))

	def hasConfiguration(self):
		for member in self.getmembers():
			if member.name.startswith(os.path.join(self.CONTENT_DIR, "CONF")):
				return True
		return False

	def restoreConfiguration(self):
		first = True

		for member in self.getmembers():
			if member.name.startswith(os.path.join(self.CONTENT_DIR, "CONF")):
				if first:
					shutil.rmtree(self.CONF_DIR, ignore_errors=True)
					os.makedirs(self.CONF_DIR)
					first = False
				dest = member.name.replace(os.path.join(self.CONTENT_DIR, "CONF"), self.CONF_DIR)

				if member.issym():
					os.symlink(member.linkname, dest)
				elif member.isdir():
					if not os.path.exists(dest):
						os.makedirs(dest, mode=member.mode)
						os.chown(dest, pwd.getpwnam(member.uname)[2], grp.getgrnam(member.gname)[2])
				else:
					self._extractFile(member, dest)

	def _hasBackend(self, backend, name=None):
		if name:
			backend = os.path.join(backend, name)

		for member in self.getmembers():
			if member.name.startswith(os.path.join(self.CONTENT_DIR, os.path.join("BACKENDS", backend))):
				return True
		return False

	def hasFileBackend(self, name=None):
		return self._hasBackend("FILE", name=name)

	def backupFileBackend(self, auto=False):
		for backend in self._getBackends("file"):
			if not auto or backend["dispatch"]:
				if not backend["dispatch"]:
					logger.warning("Backing up backend %s although it's currently not in use." % backend["name"])
				baseDir = backend["config"]["baseDir"]
				self._addContent(baseDir, sub=(baseDir, "BACKENDS/FILE/%s" % backend["name"]))

	def restoreFileBackend(self, auto=False):
		if not self.hasFileBackend():
			raise OpsiBackupBackendNotFound("No File Backend found in backup archive")

		for backend in self._getBackends("file"):
			if not auto or backend["dispatch"]:
				baseDir = backend["config"]["baseDir"]

				members = self.getmembers()

				for member in members:
					if member.name.startswith(os.path.join(self.CONTENT_DIR, "BACKENDS/FILE/%s" % backend["name"])):
						dest = member.name.replace(os.path.join(self.CONTENT_DIR, "BACKENDS/FILE/%s" % backend["name"]), baseDir)

						if member.isfile():
							self._extractFile(member, dest)
						else:
							if not os.path.exists(dest):
								os.makedirs(dest, mode=member.mode)
								os.chown(dest, pwd.getpwnam(member.uname)[2], grp.getgrnam(member.gname)[2])

	def backupDHCPBackend(self, auto=False):
		for backend in self._getBackends("dhcpd"):
			if not auto or backend["dispatch"]:
				if not backend["dispatch"]:
					logger.warning("Backing up backend %s although it's currently not in use." % backend["name"])
				self._addContent(backend["config"]['dhcpdConfigFile'], sub=(os.path.dirname(backend["config"]['dhcpdConfigFile']), "BACKENDS/DHCP/%s" % backend["name"]))

	def hasDHCPBackend(self, name=None):
		return self._hasBackend("DHCP", name=name)

	def restoreDHCPBackend(self, auto=False):
		if not self.hasDHCPBackend():
			raise OpsiBackupBackendNotFound("No DHCPD Backend found in backup archive")

		for backend in self._getBackends("dhcpd"):
			if not auto or backend["dispatch"]:
				members = self.getmembers()

				file = backend["config"]['dhcpdConfigFile']
				if os.path.exists(file):
					os.remove(file)

				for member in members:
					if member.name.startswith(os.path.join(self.CONTENT_DIR, "BACKENDS/DHCP/%s" %backend["name"])):
						self._extractFile(member, backend["config"]['dhcpdConfigFile'])

	def hasMySQLBackend(self, name=None):
		return self._hasBackend("MYSQL", name=name)

	def backupMySQLBackend(self, flushLogs=False, auto=False):
		# In Python 2.6 a deque has no "maxlen" attribute so we need to
		# work around with this.
		maximumDequeLength = 10

		for backend in self._getBackends("mysql"):
			if not auto or backend["dispatch"]:
				if not backend["dispatch"]:
					logger.warning("Backing up backend %s although it's currently not in use." % backend["name"])
				cmd = [OPSI.System.which("mysqldump")]
				cmd.append("--host=%s" % backend["config"]["address"])
				cmd.append("--user=%s" % backend["config"]["username"])
				cmd.append("--password=%s" % backend["config"]["password"])
				if flushLogs:
					logger.debug("Flushing mysql table logs.")
					cmd.append("--flush-log")
				cmd.append("--lock-tables")
				cmd.append("--add-drop-table")
				cmd.append(backend["config"]["database"])

				fd, name = tempfile.mkstemp(dir=self.tempdir)
				try:
					p = Popen(cmd, stdout=PIPE, stderr=PIPE)

					flags = fcntl.fcntl(p.stderr, fcntl.F_GETFL)
					fcntl.fcntl(p.stderr, fcntl.F_SETFL, flags| os.O_NONBLOCK)

					out = p.stdout.readline()

					try:
						collectedErrors = [p.stderr.readline()]
					except Exception:
						collectedErrors = []
					lastErrors = collections.deque(collectedErrors, maxlen=maximumDequeLength)

					while not p.poll() and out:
						os.write(fd, out)
						out = p.stdout.readline()

						try:
							currentError = p.stderr.readline().strip()
							if currentError:
								lastErrors.append(currentError)
								if not "Warning: Using a password on the command line interface can be insecure." in currentError:
									collectedErrors.append(currentError)
						except Exception:
							continue

						if maximumDequeLength == len(lastErrors):
							onlyOneErrorMessageInLastErrors = True
							firstError = lastErrors[0]
							for err in list(lastErrors)[1:]:
								if firstError != err:
									onlyOneErrorMessageInLastErrors = False
									break

							if onlyOneErrorMessageInLastErrors:
								logger.debug(
									u'Aborting: Only one message in stderr: '
									u'{0}'.format(firstError)
								)
								break

					if p.returncode not in (0, None):
						raise OpsiBackupFileError(u"MySQL dump failed for backend %s: %s" % (backend["name"], u"".join(collectedErrors)))

					self._addContent(name, (name, "BACKENDS/MYSQL/%s/database.sql" %backend["name"]))
				finally:
					os.close(fd)
					os.remove(name)

	def restoreMySQLBackend(self, auto=False):
		if not self.hasMySQLBackend():
			raise OpsiBackupBackendNotFound("No MySQL Backend found in backup archive")

		for backend in self._getBackends("mysql"):
			if not auto or backend["dispatch"]:
				fd, name = tempfile.mkstemp(dir=self.tempdir)
				os.chmod(name, 0o770)

				try:
					for member in self.getmembers():
						if member.name == os.path.join(self.CONTENT_DIR, "BACKENDS/MYSQL/%s/database.sql" % backend["name"]):
							self._extractFile(member, name)

					cmd = [OPSI.System.which("mysql")]
					#cmd.append("--max_allowed_packet=%s" % os.path.getsize(name))
					cmd.append("--host=%s" % backend["config"]["address"])
					cmd.append("--user=%s" % backend["config"]["username"])
					cmd.append("--password=%s" % backend["config"]["password"])
					cmd.append(backend["config"]["database"])

					output = StringIO.StringIO()

					p = Popen(cmd, stdin=fd, stdout=PIPE, stderr=STDOUT)

					out = p.stdout.readline()

					while not p.poll() and out:
						output.write(out)
						out = p.stdout.readline()

					if p.returncode not in (0, None):
						raise OpsiBackupFileError(u"Failed to restore MySQL Backend: %s" % output.getvalue())

				finally:
					os.close(fd)
					os.remove(name)

	def hasLDAPBackend(self):
		#TODO: LDAP-Backend will not be supported in future version. Mark deprecated.
		return False

	def backupLDAPBackend(self):
		raise NotImplementedError("LDAP backend backups are not supported yet.")

	def backupUniventionBackend(self):
		raise NotImplementedError("Univention backend backups are not supported yet.")
