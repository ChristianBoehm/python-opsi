#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = = = = = =
   =   opsi python library - BackendManager  =
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

__version__ = '1.0.1'

# Imports
import os, stat, types, re, socket, new, base64, md5
import copy as pycopy
from twisted.conch.ssh import keys

# OS dependend imports
if (os.name == 'posix'):
	import pwd, grp
	from duplicity import librsync
else:
	import win32security
	from _winreg import *

# OPSI imports
from OPSI.Product import *
from OPSI.Backend.Backend import *
from OPSI.Logger import *
from OPSI.Tools import *
from OPSI import System

# Get logger instance
logger = Logger()

HOST_GROUP = '|HOST_GROUP|'
SYSTEM_ADMIN_GROUP = 'opsiadmin'
OPSI_VERSION_FILE='/etc/opsi/version'
OPSI_MODULES_FILE='/etc/opsi/modules'

'''= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
=                                  CLASS BACKENDMANAGER                                              =
= = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = ='''

class BackendManager(DataBackend):
	
	def __init__(self, username = '', password = '', address = '', configFile=None, backend=None, authRequired=True):
		
		self._pamService = 'common-auth'
		self._sshRSAPublicKeyFile = '/etc/ssh/ssh_host_rsa_key.pub'
		
		#if os.name == 'nt':
		#	try:
		#		regroot = ConnectRegistry(None,HKEY_LOCAL_MACHINE)
		#		regpath = "SOFTWARE\\opsi.org\\opsiconfd"
		#		reg = OpenKey(regroot,regpath)
		#		windefaultdir = QueryValueEx(reg,"BaseDir")[0]
		#	except:
		#		windefaultdir = 'C:\\Programme\\opsi.org\\opsiconfd'
		#	configFile = windefaultdir+'\\backendManager.conf'
		
		''' 
		The constructor of the class BackendManager creates an instance of the
		class and initializes the backends to use. It will also read the values
		from the config file (default: /etc/opsi/backendManager.d).
		'''
		
		self.__authRequired = authRequired
		
		if self.__authRequired:
			if not username:
				raise BackendAuthenticationError("No username specified")
			if not password:
				raise BackendAuthenticationError("No password specified")
			
		self.__username = username
		self.__password = password
		self.__address = address
		
		# Default values
		self.defaultDomain = 'localdomain'

		try:
			self.defaultDomain = '.'.join(socket.getfqdn().split('.')[1:])
			logger.info("OS reports '%s' as default domain" % self.defaultDomain)
		except Exception, e:
			logger.error("Cannot get domain: %s" % e)
		
		
		self.__configFile = configFile
		self.__userGroups = []
		self.backends = {}
		
		# If a special backend is passed to the constructor, this backend
		# will be used for all function groups no matter what the config file says
		self.forcedBackend = backend
		
		# Now read the config file to overwrite the defaults
		if self.__configFile:
			self._readConfigFile()
		else:
			logger.warning("No config file given")
		
		logger.info("Using default domain '%s'" % self.defaultDomain)
		
		self._initializeBackends()
		
		self._defaultDomain = self.defaultDomain
		
		if not self.__authRequired:
			# Authenticate by remote server
			self.__userGroups = []
			logger.info("Skipping local authorization")
			
		elif re.search('^\S+\.\S+\.\S+$', self.__username):
			# Username starts with something like xxx.yyy.zzz: 
			# Assuming it is a client passing his FQDN  as username
			logger.debug("Trying to authenticate by opsiHostKey...")
			
			hostKey = self.getOpsiHostKey(self.__username)
			
			logger.confidential("Client '%s', key sent '%s', key stored '%s'" \
					% (self.__username, self.__password, hostKey))
			
			if (self.__password != hostKey):
				raise BackendAuthenticationError("opsiHostKey authentication failed for host '%s': wrong key" \
									% self.__username)
			
			self.__userGroups = [ HOST_GROUP ]
			
			if self.__username in self.getDepotIds_list():
				self.__userGroups.append( SYSTEM_ADMIN_GROUP )
			
			logger.info("opsiHostKey authentication successful for host '%s'" % self.__username)
		else:
			# System user trying to log in with username and password
			logger.debug("Trying to authenticate by Operating System...")
			self._authenticate(self.__username, self.__password)
			# Authentication did not throw exception => authentication successful
			logger.info("Operating System authentication successful for user '%s', groups '%s'" \
								% (self.__username, ','.join(self.__userGroups)))
	
		
	
	'''- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	-                                    Private Methods                                                 -
	- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -'''

	def _initializeBackends(self):
		''' This function will initialize the needed backends and asign them
		    to the function groups according to the configuration '''
		
		backendsUsed = []
		if self.forcedBackend:
			backendType = self.forcedBackend
			if isinstance(self.forcedBackend, DataBackend):
				backendType = str(self.forcedBackend.__class__).split('.')[-1][:-7]
			if not backendType in self.backends.keys():
				self.backends[backendType] = {}
		
		for (key, value) in self.backends.items():
			if self.forcedBackend:
				if isinstance(self.forcedBackend, DataBackend):
					if (key != str(self.forcedBackend.__class__).split('.')[-1][:-7]):
						continue
				elif (self.forcedBackend != key):
					continue
			
			elif not value.get('load', False):
				continue
			
			if not re.search('^[\w\d]+$', key):
				logger.error('Bad backend name: %s' % key)
				continue
			
			if not self.backends[key].get('config'):
				self.backends[key]['config'] = {}
			if not self.backends[key]['config'].get('defaultdomain'):
				self.backends[key]['config']['defaultdomain'] = self.defaultDomain
			
			logger.info("Backend config for '%s': %s" % (key, self.backends[key]['config']) )
			
			if not isinstance(self.forcedBackend, DataBackend):
				exec('from %s import %sBackend' % (key, key))
				exec('b = %sBackend(	address 	= "%s", \
							username 	= "%s", \
							password 	= "%s", \
							args 		= %s, \
							backendManager	= self )' \
					% (	key,
						self.__address,
						self.__username,
						self.__password,
						self.backends[key]['config'] ) )
				self.backends[key]['instance'] = b
			else:
				self.backends[key]['instance'] = self.forcedBackend
			
			if self.forcedBackend:
				self.forcedBackend         = key
				self.defaultBackend        = key
				self.clientManagingBackend = key
				self.pxebootconfBackend    = key
				self.passwordBackend       = key
				self.pckeyBackend          = key
				self.swinventBackend       = key
				self.hwinventBackend       = key
				self.loggingBackend        = key
			
			backendsUsed.append(key)
			logger.info("Using backend %s." % self.backends[key]['instance'].__class__)
			
			if self.forcedBackend:
				methods = []
				for pm in self.getPossibleMethods_listOfHashes():
					methods.append(pm['name'])
				
				for (n, t) in self.backends[key]['instance'].__class__.__dict__.items():
					if ( (type(t) == types.FunctionType or type(t) == types.MethodType ) and not n.startswith('_') ):
						if n in methods:
							continue
						argCount = t.func_code.co_argcount
						args = list(t.func_code.co_varnames[1:argCount])
						argDefaults = t.func_defaults
						argsWithDefaults = list(args)
						if ( argDefaults != None and len(argDefaults) > 0 ):
							offset = argCount - len(argDefaults) - 1
							for i in range( len(argDefaults) ):
								if type(argDefaults[i]) is str:
									argsWithDefaults[offset+i] = "%s='%s'" % (args[offset+i], argDefaults[i])
								else:
									argsWithDefaults[offset+i] = "%s=%s" % (args[offset+i], argDefaults[i])
						
						logger.debug("Adding instance method '%s'" % n)
						argString = ''
						if (len(args) > 0):
							argString = ', ' + ', '.join(args)
						logger.debug2('def %s(self, %s): self._execMethod(self.defaultBackend, "%s"%s)' % (n, ', '.join(argsWithDefaults), n, argString))
						exec('def %s(self, %s): return self._execMethod(self.defaultBackend, "%s"%s)' % (n, ', '.join(argsWithDefaults), n, argString))
						setattr( self.__class__, n, new.instancemethod(eval(n), None, self.__class__) )
			
		if ( len(backendsUsed) == 1 and backendsUsed[0] == 'JSONRPC' ):
			logger.warning('No authentication required!')
			# json-rpc backend is asigned to all methods
			# authentication is done by json-rpc service
			self.__authRequired = False
		
		
		
	def _authenticate(self, user, password):
		''' Authenticate a user by the underlying operating system.
		    Throws BackendAuthenticationError on failure. '''
		if (os.name == 'posix'):
			# Posix os => authenticate by PAM
			return self._pamAuthenticate(user, password)
		elif (os.name == 'nt'):
			# NT os => authenticate by windows-login
			return self._winAuthenticate(user,password)
		else:
			# Other os, not implemented yet 
			raise NotImplementedError("Sorry, operating system '%s' not supported yet!" % os.name)
		
	def _winAuthenticate(self, user, password):
		'''
		Authenticate a user by Windows-Login on current machine
		'''
		
		#Import win32 security modules
		import win32security, win32net
		
		win32security.LogonUser(user,'None',password,win32security.LOGON32_LOGON_NETWORK,win32security.LOGON32_PROVIDER_DEFAULT)
		
		'''Group-member check'''
		server = '127.0.0.1'
		groupName = SYSTEM_ADMIN_GROUP
		level = 1
		resumeHandle = 0
		prefLen = 4096
		'''list members of group 'groupName' '''
		groups = win32net.NetLocalGroupGetMembers(server, groupName , level , resumeHandle , prefLen )
		'''search in list of members for 'user' '''
		i = 0
		while i < len(groups[0]):
			if groups[0][i]['name'] == user:
				self.__userGroups.append(groupName)
				logger.debug("User '%s' is member of group '%s'" % (user, groupName))
			i = i + 1
		
	def _pamAuthenticate(self, user, password):
		''' 
		Authenticate a user by PAM (Pluggable Authentication Modules).
		Important: the uid running this code needs access to /etc/shadow 
		if os uses traditional Unix authentication mechanisms.
		'''
		logger.confidential("Trying to authenticate user '%s' with password '%s' by PAM" % (user, password))
		
		# Import PAM modules
		import PAM
		
		class AuthConv:
			''' Handle PAM conversation '''
			def __init__(_, user, password):
				_.user = user
				_.password = password
			
			def __call__(_, auth, query_list, userData=None):
				response = []
				for i in range(len(query_list)):
					(query, type) = query_list[i]
					logger.debug("PAM conversation: query '%s', type '%s'" % (query, type))
					if (type == PAM.PAM_PROMPT_ECHO_ON):
						response.append((_.user, 0))
					elif (type == PAM.PAM_PROMPT_ECHO_OFF):
						response.append((_.password, 0))
					elif (type == PAM.PAM_PROMPT_ERROR_MSG) or (type == PAM.PAM_PROMPT_TEXT_INFO):
						#print query
						response.append(('', 0));
					else:
						return None
				return response
		try:
			# Create instance
			auth = PAM.pam()
			auth.start(self._pamService)
			# Authenticate
			auth.set_item(PAM.PAM_CONV, AuthConv(user, password))
			# Set the tty
			# Workaround for:
			#   If running as daemon without a tty the following error
			#   occurs with older versions of pam:
			#      pam_access: couldn't get the tty name
			try:
				auth.set_item(PAM.PAM_TTY, '/dev/null')
			except:
				pass
			auth.authenticate()
			auth.acct_mgmt()
			
			self.__userGroups = [ grp.getgrgid( pwd.getpwnam(user)[3] )[0] ]
			logger.debug("Primary group of user '%s' is '%s'" % (user, self.__userGroups[0]))
			groups = grp.getgrall()
			for group in groups:
				if user in group[3]:
					self.__userGroups.append(group[0])
					logger.debug("User '%s' is member of group '%s'" % (user, group[0]))
		
		except Exception, e:
			# Something failed => raise authentication error
			raise BackendAuthenticationError("PAM authentication failed for user '%s': %s" % (user, e))
		
		
	def _readConfigFile(self):
		''' Get settings from config file '''
		try:
			# Read Config-File
			confFiles = [ self.__configFile ]
			if os.path.isdir(self.__configFile):
				confFiles = []
				files = os.listdir(self.__configFile)
				files.sort()
				for f in files:
					if f.endswith('.conf'):
						confFiles.append( os.path.join(self.__configFile, f) )
			
			try:
				for confFile in confFiles:
					logger.info("Reading config file '%s'" % confFile)
					st = os.stat(confFile)
					mode = st[stat.ST_MODE] & 0777
					if (mode & 0007 != 0):
						logger.critical("Check file permissions of '%s'." % confFile + 
								 " File permissions are: '%s', should not be world readable!" %
								 oct(mode) )
					
					
					execfile(confFile)
			except Exception, e:
				raise Exception("error reading file '%s': %s" % (confFile, e))
			
			for (key, val) in locals().items():
				if ( type(val) == types.FunctionType ):
					logger.debug("Adding instancemethod: '%s'" % key )
					setattr( self.__class__, key, new.instancemethod(val, None, self.__class__) )
		except Exception, e:
			raise Exception("Failed to read config from '%s': %s" % (self.__configFile, e))
	
	def __readConfigFromReg(self):
		''' Getting setting from Windows Registry '''
		try:
			regroot = ConnectRegistry(None,HKEY_LOCAL_MACHINE)
			regpath = "SOFTWARE\\opsi.org\\opsiconfd"
			reg = OpenKey(regroot,regpath)
			# Read Reg-Values
			self.backends[BACKEND_FILE]['config']['pclogDir'] = QueryValueEx(reg,"pclogDir")[0]
			self.backends[BACKEND_FILE]['config']['pcpatchDir'] = QueryValueEx(reg,"pcpatchDir")[0]
			self.backends[BACKEND_FILE]['config']['depotDir'] = QueryValueEx(reg,"depotDir")[0]
			self.backends[BACKEND_FILE]['config']['productsFile'] = QueryValueEx(reg,"productsFile")[0]
			self.backends[BACKEND_FILE]['config']['groupsFile'] = QueryValueEx(reg,"groupsFile")[0]
			self.backends[BACKEND_FILE]['config']['licensesFile'] = QueryValueEx(reg,"licensesFile")[0]
			self.backends[BACKEND_FILE]['config']['pckeyFile'] = QueryValueEx(reg,"pckeyFile")[0]
			self.backends[BACKEND_FILE]['config']['opsiTFTPDir'] = QueryValueEx(reg,"opsiTFTPDir")[0]
		except Exception, e:
			logger.warning("Failed to read Registry: %s" % e)
		
	def _verifyGroupMembership(self, *groups):
		if not self.__authRequired: 
			return
		
		temp = []
		for group in groups:
			if group:
				temp.append(group)
		groups = temp
		
		allow = False
		for group in groups:
			if group in self.__userGroups:
				allow = True
				break
		if not allow:
			raise BackendPermissionDeniedError("Access denied for user '%s': Group membership '%s' required!" \
								% (self.__username, ' or '.join(groups)))
	
	def _verifyUser(self, *userIds):
		if not self.__authRequired: 
			return
		
		temp = []
		for userId in userIds:
			if userId:
				temp.append(userId)
		userIds = temp
		
		allow = False
		for userId in userIds:
			if (userId == self.__username):
				allow = True
				break
		logger.debug("Username '%s' currently stored, '%s' required." % (self.__username, ' or '.join(userIds)))
		if not allow:
			raise BackendPermissionDeniedError("Access denied: Connection as user '%s' required, logged in as '%s'!" % (' or '.join(userIds), self.__username ) )
	
	def _execMethod(self, backend=None, method=None, *params):
		if self.forcedBackend:
			backend = self.forcedBackend
		
		if not backend:
			raise BackendBadValueError('neither backend given nor backend forced!')
		
		if not method:
			raise BackendBadValueError('No methodname given!')
		
		params = str(params)
		if params.endswith(',)'):
			params = params[:-2] + ')'
		
		if (type(backend) != list):
			backend = [ backend ]
		
		result = None
		for be in backend:
			b = self.backends.get(be)
			if not b:
				raise Exception("Backend '%s' not defined!" % be)
			instance = self.backends[be].get('instance')
			if not instance:
				raise Exception("Backend '%s' not loaded!" % be)
			
			logger.debug("backend '%s' => executing: b.%s%s" % (instance.__class__, method, params))
			res = eval( "instance.%s%s" % (method, params) )
			if (result == None):
				result = res
			
			elif ( type(res) == list ) and ( type(result) == list ):
				result.extend(res)
			
			elif ( type(res) == dict ) and ( type(result) == dict ):
				for (key, value) in res.items():
					result[key] = value
			
			elif (( type(res) == str ) or ( type(res) == unicode )) and (( type(result) == str ) or ( type(result) == unicode )):
				if res:
					result += "\n" + res
			
			elif (res != None):
				result = res
		return result
	
	'''- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -
	-                                    Public Methods                                                  -
	- - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - - -'''
	def exit(self):
		for (name, backend) in self.backends.items():
			instance = backend.get('instance')
			if instance:
				logger.debug("%s: exit()" % name)
				instance.exit()
	
	def checkForErrors(self):
		self._verifyGroupMembership(SYSTEM_ADMIN_GROUP)
		
		res = {}
		for (name, backend) in self.backends.items():
			if not backend.get('load', False):
				continue
			res[name] = []
			instance = backend.get('instance')
			if instance:
				logger.debug("%s: checkForErrors()" % name)
				res[name] = instance.checkForErrors()
		return res
	
	def getMD5Sum(self, filename):
		self._verifyGroupMembership(SYSTEM_ADMIN_GROUP)
		
		try:
			res = md5sum(filename)
			logger.info("MD5sum of file '%s' is '%s'" % (filename, res))
			return res
		except Exception, e:
			raise BackendIOError("Failed to get md5sum: %s" % e)
	
	def librsyncSignature(self, filename):
		self._verifyGroupMembership(SYSTEM_ADMIN_GROUP)
		
		if (os.name != 'posix'):
			raise NotImplementedError("Not implemented for non-posix os")
		
		(f, sf) = (None, None)
		try:
			f = open(filename, 'rb')
			sf = librsync.SigFile(f)
			sig = base64.encodestring(sf.read())
			f.close()
			sf.close()
			return sig
		except Exception, e:
			if f: f.close()
			if sf: sf.close()
			raise BackendIOError("Failed to get librsync signature: %s" % e)
		
	def librsyncPatchFile(self, oldfile, deltafile, newfile):
		self._verifyGroupMembership(SYSTEM_ADMIN_GROUP)
		
		if (os.name != 'posix'):
			raise NotImplementedError("Not implemented for non-posix os")
		
		logger.debug("librsyncPatchFile: %s, %s, %s" % (oldfile, deltafile, newfile))
		if (oldfile == newfile):
			raise BackendBadValueError("oldfile and newfile are the same file")
		if (deltafile == newfile):
			raise BackendBadValueError("deltafile and newfile are the same file")
		if (deltafile == oldfile):
			raise BackendBadValueError("oldfile and deltafile are the same file")
		
		(of, df, nf, pf) = (None, None, None, None)
		bufsize = 1024*1024
		try:
			of = open(oldfile, "rb")
			df = open(deltafile, "rb")
			nf = open(newfile, "wb")
			pf = librsync.PatchedFile(of, df)
			data = True
			while(data):
				data = pf.read(bufsize)
				nf.write(data)
			nf.close()
			pf.close()
			df.close()
			of.close()
		except Exception, e:
			if nf: nf.close()
			if pf: pf.close()
			if df: df.close()
			if of: of.close()
			raise BackendIOError("Failed to patch file: %s" % e)
	
	def getDiskSpaceUsage(self, path):
		self._verifyGroupMembership(SYSTEM_ADMIN_GROUP)
		
		if (os.name != 'posix'):
			raise NotImplementedError("Not implemented for non-posix os")
		
		try:
			return System.getDiskSpaceUsage(path)
		except Exception, e:
			raise BackendIOError("Failed to get disk space usage: %s" % e)
	
	def getHostRSAPublicKey(self):
		self._verifyGroupMembership(SYSTEM_ADMIN_GROUP, HOST_GROUP)
		
		if (os.name != 'posix'):
			raise NotImplementedError("Not implemented for non-posix os")
		
		f = open(self._sshRSAPublicKeyFile, 'r')
		data = f.read()
		f.close()
		return data
	
	def getPcpatchRSAPrivateKey(self):
		self._verifyGroupMembership(SYSTEM_ADMIN_GROUP, HOST_GROUP)
		
		if (os.name != 'posix'):
			raise NotImplementedError("Not implemented for non-posix os")
		
		sshDir = os.path.join(pwd.getpwnam("pcpatch")[5], '.ssh')
		pcpatchUid = pwd.getpwnam("pcpatch")[2]
		pcpatchGid = grp.getgrnam("pcpatch")[2]
		idRsa = os.path.join(sshDir, 'id_rsa')
		idRsaPub = os.path.join(sshDir, 'id_rsa.pub')
		authorizedKeys = os.path.join(sshDir, 'authorized_keys')
		if not os.path.exists(sshDir):
			mkdir(sshDir, 0750)
			os.chown(sshDir, pcpatchUid, pcpatchGid)
		if not os.path.exists(idRsa):
			logger.notice("Creating RSA private key for user pcpatch in '%s'" % idRsa)
			execute("%s -N '' -t rsa -f %s" % ( which('ssh-keygen'), idRsa))
			os.chmod(idRsa, 0640)
			os.chown(idRsa, pcpatchUid, pcpatchGid)
			os.chmod(idRsaPub, 0644)
			os.chown(idRsaPub, pcpatchUid, pcpatchGid)
		if not os.path.exists(authorizedKeys):
			f = open(idRsaPub, 'r')
			f2 = open(authorizedKeys, 'w')
			f2.write(f.read())
			f2.close()
			f.close()
			os.chmod(authorizedKeys, 0600)
			os.chown(authorizedKeys, pcpatchUid, pcpatchGid)
		f = open(idRsa, 'r')
		data = f.read()
		f.close()
		return data
	
	def getBackendInfos_listOfHashes(self):
		self._verifyGroupMembership(SYSTEM_ADMIN_GROUP)
		
		infos = []
		for (name, backend) in self.backends.items():
			config = backend.get('config')
			if config:
				for key in config.keys():
					if (key.lower() == "bindpw"):
						config[key] = '*******'
			info = { 
				'name':		name,
				'config':	config,
				'version':	'not available',
				'module':	'not loaded' }
			
			instance = backend.get('instance')
			if instance:
				info['module'] = instance.__module__
				exec( "import %s" % instance.__module__ )
				info['version'] = eval("%s.__version__" % instance.__module__)
			
			infos.append(info)
		
		return infos
	
	def authenticated(self):
		''' Checks if a user has been successfuly authenticated.
		    Raises an exception if not. '''
		return True
	
	def userIsAdmin(self):
		if SYSTEM_ADMIN_GROUP in self.__userGroups:
			return True
		return False
	
	def userIsHost(self):
		if HOST_GROUP in self.__userGroups:
			return True
		return False
	
	def installPackage(self, filename, force=False, defaultProperties={}, tempDir=None):
		self._verifyGroupMembership(SYSTEM_ADMIN_GROUP)
		
		if not os.path.isfile(filename):
			raise BackendIOError("Package file '%s' does not exist" % filename)
		
		if not defaultProperties:
			defaultProperties = {}
		
		logger.info("Installing package file '%s'" % filename)
		
		ppf = Product.ProductPackageFile(filename, tempDir=tempDir)
		
		depotId = socket.getfqdn()
		depot = self.getDepot_hash(depotId)
		
		clientDataDir = depot['depotLocalUrl']
		if not clientDataDir.startswith('file:///'):
			raise BackendBadValueError("Value '%s' not allowed for depot local url (has to start with 'file:///')" % clientDataDir)
		clientDataDir = os.path.join(clientDataDir[7:], ppf.product.productId)
		
		logger.info("Setting client data dir to '%s'" % clientDataDir)
		ppf.setClientDataDir(clientDataDir)
		
		lockedOnDepots = self.getProductLocks_hash(depotIds = [ depotId ]).get(ppf.product.productId, [])
		logger.info("Product currently locked on : %s" % lockedOnDepots)
		if depotId in lockedOnDepots and not force:
			logger.info("Cleaning up")
			ppf.cleanup()
			raise BackendTemporaryError("Product '%s' currently locked on depot '%s'" % (ppf.product.productId, depotId))
		
		logger.info("Locking product '%s' on depot '%s'" % (ppf.product.productId, depotId))
		self.lockProduct(ppf.product.productId, depotIds=[ depotId ])
		
		try:
			exists = ppf.product.productId in self.getProductIds_list(objectId = depotId, installationStatus = 'installed')
			if exists:
				logger.warning("Product '%s' already exists in database" % ppf.product.productId)
			
			logger.info("Checking dependencies of product '%s'" % ppf.product.productId)
			ppf.checkDependencies(configBackend=self)
			
			logger.info("Running preinst of product '%s'" % ppf.product.productId)
			for line in ppf.runPreinst():
				logger.info(" -> %s" % line)
			
			if exists:
				# Delete existing product dependencies
				logger.info("Deleting product dependencies of product '%s'" % ppf.product.productId)
				self.deleteProductDependency(ppf.product.productId, depotIds = [ depotId ])
				
				# Delete productPropertyDefinitions
				logger.info("Deleting product property definitions of product '%s'" % ppf.product.productId)
				self.deleteProductPropertyDefinitions(ppf.product.productId, depotIds = [ depotId ])
				
				# Not deleting product, because this would delete client productstates as well
			
			if ppf.incremental:
				logger.info("Incremental package, not deleting old client files")
			else:
				logger.info("Deleting old client files")
				ppf.deleteClientDataDir()
			
			logger.info("Unpacking package '%s'" % filename)
			ppf.unpack()
			
			ppf.writeFileInfoFile()
			
			ppf.setAccessRights()
			
			logger.info("Creating product in database")
			self.createProduct(
					ppf.product.productType,
					ppf.product.productId,
					ppf.product.name,
					ppf.product.productVersion,
					ppf.product.packageVersion,
					ppf.product.licenseRequired,
					ppf.product.setupScript,
					ppf.product.uninstallScript,
					ppf.product.updateScript,
					ppf.product.alwaysScript,
					ppf.product.onceScript,
					ppf.product.priority,
					ppf.product.description,
					ppf.product.advice,
					ppf.product.productClassNames,
					ppf.product.pxeConfigTemplate,
					ppf.product.windowsSoftwareIds,
					depotIds = [ depotId ] )
			
			
			if (ppf.product.productType != 'server'):
				for d in ppf.product.productDependencies:
					self.createProductDependency(
						d.productId,
						d.action,
						d.requiredProductId,
						d.requiredProductClassId,
						d.requiredAction,
						d.requiredInstallationStatus,
						d.requirementType,
						depotIds = [ depotId ]
					)
			
				properties = {}
				for p in ppf.product.productProperties:
					defaultValue = p.defaultValue
					if p.name in defaultProperties.keys():
						defaultValue = defaultProperties[p.name]
					
					self.createProductPropertyDefinition(
						p.productId,
						p.name,
						p.description,
						defaultValue,
						p.possibleValues,
						depotIds = [ depotId ]
					)
					properties[p.name] = defaultValue
				
				#if properties:
				#	bm.setProductProperties(p.productId, properties, objectId = depotId)
				
				# TODO: needed?
				logger.info("Setting product-installation-status on depot '%s' to installed" % depotId )
				self.setProductInstallationStatus(ppf.product.productId, depotId, 'installed')
			
			logger.info("Running postinst of product '%s'" % ppf.product.productId)
			for line in ppf.runPostinst():
				logger.info(" -> %s" % line)
			
			logger.info("Cleaning up")
			ppf.cleanup()
			
			logger.info("Unlocking product '%s' on depot '%s'" % (ppf.product.productId, depotId))
			self.unlockProduct(ppf.product.productId, depotIds=[ depotId ])
			
		except Exception, e:
			try:
				logger.info("Cleaning up")
				ppf.cleanup()
				# TODO: unlock if failed?
				logger.info("Unlocking product '%s' on depot '%s'" % (ppf.product.productId, depotId))
				self.unlockProduct(ppf.product.productId, depotIds=[ depotId ])
			except Exception, e2:
				logger.error(e2)
			logger.logException(e)
			raise e
	
	def uninstallPackage(self, productId, force=False, deleteFiles=True):
		self._verifyGroupMembership(SYSTEM_ADMIN_GROUP)
		
		logger.info("Uninstalling package '%s'" % productId)
		
		depotId = socket.getfqdn()
		depot = self.getDepot_hash(depotId)
		
		if not productId in self.getProductIds_list(objectId = depotId, installationStatus = 'installed'):
			raise BackendBadValueError("Product '%s' is not installed on depot '%s'" % (productId, depotId))
		
		lockedOnDepots = self.getProductLocks_hash(depotIds = [ depotId ]).get(productId, [])
		logger.info("Product currently locked on : %s" % lockedOnDepots)
		if depotId in lockedOnDepots and not force:
			raise BackendTemporaryError("Product '%s' currently locked on depot '%s'" % (productId, depotId))
		
		self.lockProduct(productId, depotIds=[ depotId ])
		
		logger.debug("Deleting product '%s'" % productId)
		
		self.setProductInstallationStatus(productId, objectId = depotId, installationStatus = 'uninstalled')
		self.deleteProductDependency(productId, depotIds = [ depotId ])
		self.deleteProductProperties(productId, objectId = depotId)
		self.deleteProduct(productId, depotIds = [ depotId ])
		
		if deleteFiles:
			clientDataDir = depot['depotLocalUrl']
			if not clientDataDir.startswith('file:///'):
				raise BackendBadValueError("Value '%s' not allowed for depot local url (has to start with 'file:///')" % clientDataDir)
			clientDataDir = os.path.join(clientDataDir[7:], productId)
			
			logger.info("Deleting client data dir '%s'" % clientDataDir)
			rmdir(clientDataDir, recursive=True)
		
		self.unlockProduct(productId, depotIds=[ depotId ])
		
	
	def areDepotsSynchronous(self, depotIds=[]):
		knownDepotIds = self.getDepotIds_list()
		if not depotIds:
			depotIds = knownDepotIds
		
		if not type(depotIds) in (list, tuple):
			raise BackendBadValueError("Type of depotIds has to be list")
		
		#locks = self.getProductLocks_hash(depotIds = depotIds)
		
		products = {}
		depotProducts = {}
		for depotId in depotIds:
			depotProducts[depotId] = {}
			if not depotId in knownDepotIds:
				raise BackendMissingDataError("Unkown depot '%s'" % depotId)
			for product in self.getProducts_listOfHashes(depotId = depotId):
				productId = product['productId']
				depotProducts[depotId][productId] = product
				if not productId in products.keys():
					products[productId] = {
						'productVersion': None,
						'packageVersion': None
					}
		
		logger.info("Known product ids: %s" % ', '.join(products.keys()))
		for depotId in depotIds:
			logger.info("Processing depot '%s'" % depotId)
			for productId in products.keys():
				try:
					product = depotProducts[depotId][productId]
				except Exception, e:
					logger.notice("Depots %s not synchronous: product '%s' not available on depot '%s': %s" \
						% (', '.join(depotIds), productId, depotId, e))
					return False
				logger.debug("Product info for product '%s' on depot '%s': %s" % (productId, depotId, product))
				if not products[productId]['productVersion']:
					products[productId]['productVersion'] = product.get('productVersion')
				elif (products[productId]['productVersion'] != product.get('productVersion')):
					logger.notice("Depots %s not synchronous: product '%s': product version seen: '%s', product version on depot '%s': '%s'" \
						% (', '.join(depotIds), productId, products[productId]['productVersion'], depotId, product.get('productVersion')))
					return False
				
				if not products[productId]['packageVersion']:
					products[productId]['packageVersion'] = product.get('packageVersion')
				elif (products[productId]['packageVersion'] != product.get('packageVersion')):
					logger.notice("Depots %s not synchronous: product '%s': package version seen: '%s', package version on depot '%s': '%s'" \
						% (', '.join(depotIds), productId, products[productId]['packageVersion'], depotId, product.get('packageVersion')))
					return False
		return True
	
	def adjustProductStates(self, productStates, objectIds=[], options={}):
		logger.debug("adjusting product states")
		if not productStates:
			return {}
		if not objectIds:
			raise BackendBadValueError("No object ids given")
		if not options:
			options = {}
		
		options['processPriorities'] = options.get('processPriorities', True)
		options['processDependencies'] = options.get('processDependencies', False)
		options['forceAccorateSequence'] = options.get('forceAccorateSequence', False)
		
		if options['processPriorities'] or options['processDependencies']:
			opts = dict(options)
			opts['processPriorities'] = False
			opts['processDependencies'] = False
			allProductStates = self.getProductStates_hash(objectIds, options=opts)
			
			# TODO: optimize for speed
			allProducts = {}
			allProductDependencies = {}
			hostToDepot = {}
			for hostId in objectIds:
				depotId = self.getDepotId(hostId)
				hostToDepot[hostId] = depotId
				if depotId in allProducts.keys():
					continue
				allProducts[depotId] = {}
				allProductDependencies[depotId] = {}
				for productId in self.getProductIds_list(objectId = depotId):
					allProducts[depotId][productId] = self.getProduct_hash(productId = productId, depotId = depotId)
					allProductDependencies[depotId][productId] = self.getProductDependencies_listOfHashes(productId = productId, depotId = depotId)
				
			for hostId in objectIds:
				products = {}
				sequence = []
				for productState in allProductStates[hostId]:
					productId = productState['productId']
					sequence.append(productId)
					depotId = hostToDepot[hostId]
					products[productId] = pycopy.deepcopy(allProducts[depotId][productId])
					products[productId]['state'] = productState
					products[productId]['dependencies'] = pycopy.deepcopy(allProductDependencies[depotId][productId])
					for ps in productStates[hostId]:
						if (ps['productId'] == productId):
							if ps.get('installationStatus'):
								products[productId]['state']['installationStatus'] = ps['installationStatus']
							if ps.get('actionRequest'):
								products[productId]['state']['actionRequest'] = ps['actionRequest']
							break
				
				if options['processPriorities']:
					# Sort by priority
					priorityToProductIds = {}
					sequence = []
					for (productId, product) in products.items():
						priority = int(products[productId]['priority'])
						if not priorityToProductIds.has_key(priority):
							priorityToProductIds[priority] = []
						priorityToProductIds[priority].append(productId)
					priorities = priorityToProductIds.keys()
					priorities.sort()
					priorities.reverse()
					for priority in priorities:
						sequence.extend(priorityToProductIds[priority])
				
					logger.debug("Sequence after priority sorting:")
					for productId in sequence:
						logger.debug("   %s (%s)" % (productId, products[productId]['priority']))
					
				if options['processDependencies']:
					# Add dependent products
					def addActionRequest(productId, actionRequest):
						logger.debug("Adding action request '%s' for product '%s'" % (actionRequest, productId))
						products[productId]['state']['actionRequest'] = actionRequest
						for dependency in products[productId]['dependencies']:
							if (dependency['action'] != actionRequest):
								continue
							if not products.has_key(dependency['requiredProductId']):
								logger.warning("Got a dependency to an unkown product %s, ignoring!" % dependency['requiredProductId'])
								continue
							logger.debug("   Product '%s' defines a dependency to product '%s' for action '%s'" \
									% (productId, dependency['requiredProductId'], actionRequest))
							requiredAction = dependency['requiredAction']
							if not requiredAction:
								if (dependency['requiredInstallationStatus'] == products[dependency['requiredProductId']]['state']['installationStatus']):
									continue
								elif (dependency['requiredInstallationStatus'] == 'installed'):
									requiredAction = 'setup'
								elif (dependency['requiredInstallationStatus'] == 'not_installed'):
									requiredAction = 'uninstall'
							if (products[dependency['requiredProductId']]['state']['actionRequest'] == requiredAction):
								continue
							elif products[dependency['requiredProductId']]['state']['actionRequest'] not in ('undefined', 'none'):
								raise BackendUnaccomplishableError("Cannot fulfill actions '%s' and '%s' for product '%s'" \
									% (products[dependency['requiredProductId']]['state']['actionRequest'], requiredAction, dependency['requiredProductId']))
							addActionRequest(dependency['requiredProductId'], requiredAction)
					
					for (productId, product) in products.items():
						if product['state']['actionRequest'] in ('none', 'undefined'):
							continue
						addActionRequest(productId, product['state']['actionRequest'])
				
					# Sort by dependencies
					for run in (1, 2):
						for (productId, product) in products.items():
							if product['state']['actionRequest'] in ('none', 'undefined'):
								continue
							logger.debug("Correcting sequence of action request '%s' for product '%s'" % (product['state']['actionRequest'], productId))
							for dependency in products[productId]['dependencies']:
								if (dependency['action'] != product['state']['actionRequest']):
									continue
								if not products.has_key(dependency['requiredProductId']):
									logger.warning("Got a dependency to an unkown product %s, ignoring!" % dependency['requiredProductId'])
									continue
								logger.debug("   Product '%s' defines a dependency to product '%s' for action '%s'" \
										% (productId, dependency['requiredProductId'], product['state']['actionRequest']))
								if not dependency['requirementType']:
									continue
								(ppos, dpos) = (0, 0)
								for i in range(len(sequence)):
									if (sequence[i] == productId):
										ppos = i
									elif (sequence[i] == dependency['requiredProductId']):
										dpos = i
								if (dependency['requirementType'] == 'before') and (ppos < dpos):
									if (run == 2):
										raise BackendUnaccomplishableError("Cannot resolve sequence for products '%s', '%s'" \
														% (productId, dependency['requiredProductId']))
									sequence.remove(dependency['requiredProductId'])
									sequence.insert(ppos, dependency['requiredProductId'])
								elif (dependency['requirementType'] == 'after') and (dpos < ppos):
									if (run == 2):
										raise BackendUnaccomplishableError("Cannot resolve sequence for products '%s', '%s'" \
														% (productId, dependency['requiredProductId']))
									sequence.remove(dependency['requiredProductId'])
									sequence.insert(ppos+1, dependency['requiredProductId'])
						logger.debug("Sequence after dependency sorting (run %d):" % run)
						for productId in sequence:
							logger.debug("   %s (%s)" % (productId, products[productId]['priority']))
						if not options['forceAccorateSequence']:
							break
						
				productStates[hostId] = []
				for productId in sequence:
					state = products[productId]['state']
					state['productId'] = productId
					productStates[hostId].append(state)
		
		# Other options
		for (key, values) in options.items():
			if (key == 'actionProcessingFilter'):
				logger.debug("action processing filter found")
				for (k, v) in values.items():
					if (k == "productIds"):
						productIds = v
						if not type(productIds) is list:
							productIds = [productIds]
						for hostId in productStates.keys():
							for i in range(len(productStates[hostId])):
								if not productStates[hostId][i]['productId'] in productIds:
									productStates[hostId][i]['actionRequest'] = 'none'
					else:
						logger.warning("adjustProductStates: unkown key '%s' in %s options" % (k, key))
			elif not key in ('processDependencies', 'processPriorities', 'forceAccorateSequence'):
				logger.warning("adjustProductStates: unkown key '%s' in options" % key)
		
		return productStates
		
	def adjustProductActionRequests(self, productActionRequests, hostId='', options={}):
		logger.debug("adjusting product action requests")
		if not productActionRequests:
			return []
		if not hostId:
			raise BackendBadValueError("No host id given")
		if not options:
			options = {}
		
		productStates = {}
		productStates[hostId] = productActionRequests
		productActionRequests = []
		for productState in self.adjustProductStates(productStates = productStates, objectIds = [hostId], options = options)[hostId]:
			productActionRequests.append( {'productId': productState['productId'], 'actionRequest': productState['actionRequest']} )
		return productActionRequests
	
	def getOpsiInformation_hash(self):
		opsiVersion = 'unknown'
		try:
			f = open(OPSI_VERSION_FILE, 'r')
			opsiVersion = f.readline().strip()
			f.close()
		except Exception, e:
			logger.error("Failed to read version info from file '%s': %s" % (OPSI_VERSION_FILE, e))
		
		modules = {}
		try:
			modules['valid'] = False
			f = open(OPSI_MODULES_FILE, 'r')
			for line in f.readlines():
				line = line.strip()
				if (line.find('=') == -1):
					logger.error("Found bad line '%s' in modules file '%s'" % (line, OPSI_MODULES_FILE))
					continue
				(module, state) = line.split('=', 1)
				module = module.strip().lower()
				state = state.strip()
				if (module == 'signature'):
					modules[module] = long(state)
					continue
				if (module == 'customer'):
					modules[module] = state
					continue
				state = state.lower()
				if not state in ('yes', 'no'):
					logger.error("Found bad line '%s' in modules file '%s'" % (line, OPSI_MODULES_FILE))
					continue
				modules[module] = (state == 'yes')
			f.close()
			if not modules.get('signature'):
				modules = {'valid': False}
				raise Exception('Signature not found')
			if not modules.get('customer'):
				modules = {'valid': False}
				raise Exception('Customer not found')
			
			publicKey = keys.getPublicKeyObject(data = base64.decodestring('AAAAB3NzaC1yc2EAAAADAQABAAABAQCAD/I79Jd0eKwwfuVwh5B2z+S8aV0C5suItJa18RrYip+d4P0ogzqoCfOoVWtDojY96FDYv+2d73LsoOckHCnuh55GA0mtuVMWdXNZIE8Avt/RzbEoYGo/H0weuga7I8PuQNC/nyS8w3W8TH4pt+ZCjZZoX8S+IizWCYwfqYoYTMLgB0i+6TCAfJj3mNgCrDZkQ24+rOFS4a8RrjamEz/b81noWl9IntllK1hySkR+LbulfTGALHgHkDUlk0OSu+zBPw/hcDSOMiDQvvHfmR4quGyLPbQ2FOVm1TzE0bQPR+Bhx4V8Eo2kNYstG2eJELrz7J1TJI0rCjpB+FQjYPsP'))
			data = ''
			mks = modules.keys()
			mks.sort()
			for module in mks:
				if module in ('valid', 'signature'):
					continue
				val = modules[module]
				if (val == False): val = 'no'
				if (val == True):  val = 'yes'
				data += module.lower().strip() + ' = ' + val + '\r\n'
			modules['valid'] = bool(publicKey.verify(md5.new(data).digest(), [ modules['signature'] ]))
		except Exception, e:
			logger.error("Failed to read opsi modules file '%s': %s" % (OPSI_MODULES_FILE, e))
		
		return {
			"opsiVersion": opsiVersion,
			"modules":     modules
		}
		
	def getPossibleMethods_listOfHashes(self):
		''' This function returns a list of available interface methods.
		The methods are defined by hashes containing the keys "name" and
		"params", which is a list of parameter names used for a method.
		Parameters starting with an asterisk (*) are optional '''
		methodList = []
		methods = {}
		for (n, t) in Backend.__dict__.items():
			# Extract a list of all "public" functions (functionname does not start with '_') 
			if ( (type(t) == types.FunctionType or type(t) == types.MethodType )
			      and not n.startswith('_') ):
				methods[n] = t
		
		for (n, t) in DataBackend.__dict__.items():
			# Extract a list of all "public" functions (functionname does not start with '_') 
			if ( (type(t) == types.FunctionType or type(t) == types.MethodType )
			      and not n.startswith('_') ):
				methods[n] = t
		
		for (n, t) in self.__class__.__dict__.items():
			# Extract a list of all "public" functions (functionname does not start with '_') 
			if ( (type(t) == types.FunctionType or type(t) == types.MethodType )
			      and not n.startswith('_') ):
				methods[n] = t
		
		for (n, t) in methods.items():
				argCount = t.func_code.co_argcount
				argNames = list(t.func_code.co_varnames[1:argCount])
				argDefaults = t.func_defaults
				if ( argDefaults != None and len(argDefaults) > 0 ):
					offset = argCount - len(argDefaults) - 1
					for i in range( len(argDefaults) ):
						argNames[offset+i] = '*' + argNames[offset+i]		
				methodList.append( { 'name': n, 'params': argNames} )
		
		# Sort the function list by name
		methodList.sort()
		return methodList
	
	
	
