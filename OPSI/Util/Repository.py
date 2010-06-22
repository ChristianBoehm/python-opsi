#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = = = = =
   =   opsi python library - Repository    =
   = = = = = = = = = = = = = = = = = = = = =
   
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

__version__ = '4.0'

# Imports
import re, stat, base64, urllib, httplib, os, shutil

from OPSI.web2 import responsecode
from OPSI.web2.dav import davxml

# OPSI imports
from OPSI.Logger import *
from OPSI.Types import *
from OPSI.Util.Message import ProgressSubject
from OPSI.Util import md5sum, non_blocking_connect_http, non_blocking_connect_https
from OPSI.Util.File.Opsi import PackageContentFile

# Get Logger instance
logger = Logger()

def _(string):
	return string

# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =
# =       Repositories                                                                =
# = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = = =

def getRepository(url, username=u'', password=u'', maxBandwidth=0, dynamicBandwidth=False, application=''):
	url          = forceUnicode(url)
	username     = forceUnicode(username)
	password     = forceUnicode(password)
	maxBandwidth = forceInt(maxBandwidth)
	if re.search('^file://', url):
		return FileRepository(url, username, password, maxBandwidth, dynamicBandwidth, application)
	if re.search('^https?://', url):
		return HTTPRepository(url, username, password, maxBandwidth, dynamicBandwidth, application)
	if re.search('^webdavs?://', url):
		return WebDAVRepository(url, username, password, maxBandwidth, dynamicBandwidth, application)
	raise RepositoryError(u"Repository url '%s' not supported" % url)

class Repository:
	def __init__(self, url, username=u'', password=u'', maxBandwidth=0, dynamicBandwidth=False, application=''):
		'''
		maxBandwith must be in byte/s
		'''
		self._url              = forceUnicode(url)
		self._username         = forceUnicode(username)
		self._password         = forceUnicode(password)
		self._path             = u''
		self._maxBandwidth     = forceInt(maxBandwidth)
		self._dynamicBandwidth = forceBool(dynamicBandwidth)
		self._application  = 'opsi repository module version %s' % __version__
		if application:
			self._application = str(application)
		
		if (self._maxBandwidth < 0):
			self._maxBandwidth = 0
		
		self._dynamicBandwidthLimit = 0.0
		self._dynamicBandwidthLimitTime = None
		self._dynamicBandwidthNoLimitTime = None
		self._lastUnlimitedSpeed = 0.0
		self._bandwidthSleepTime = 0.0
		
		self._networkPerformanceCounter = None
		if self._dynamicBandwidth:
			from OPSI.System import getDefaultNetworkInterfaceName, NetworkPerformanceCounter
			self._networkPerformanceCounter = NetworkPerformanceCounter(getDefaultNetworkInterfaceName())
	
	def __del__(self):
		if self._networkPerformanceCounter:
			try:
				self._networkPerformanceCounter.stop()
			except:
				pass
		
	def __unicode__(self):
		return u'<%s %s>' % (self.__class__.__name__, self._url)
	
	def __str__(self):
		return unicode(self).encode("utf-8")
	
	__repr__ = __unicode__
	
	def _sleepForBandwidth(self):
		bwlimit = 0.0
		
		if (self._averageSpeed == 0):
			return
		if not (self._dynamicBandwidth and self._networkPerformanceCounter) and not self._maxBandwidth:
			return
		
		if self._dynamicBandwidth and self._networkPerformanceCounter:
			now = time.time()
			networkUsage = 0
			if (self._transferDirection == 'out'):
				networkUsage = self._networkPerformanceCounter.getBytesOutPerSecond()
			else:
				networkUsage = self._networkPerformanceCounter.getBytesInPerSecond()
			
			if (networkUsage > 0):
				usage = float(self._currentSpeed)/float(networkUsage)
				logger.debug2("Current %0.2f kByte/s, average %0.2f kByte/s, total network usage %0.2f kByte/s, using %0.2f%% of total bandwidth" \
					% ((self._currentSpeed/1024), (self._averageSpeed/1024), (networkUsage/1024), usage*100))
				
				if self._dynamicBandwidthLimit:
					bwlimit = self._dynamicBandwidthLimit
					if (usage >= 0.90) or ((usage >= 0.70) and (self._lastUnlimitedSpeed/networkUsage > 2)):
						self._dynamicBandwidthLimitTime = None
						if self._dynamicBandwidthNoLimitTime:
							delta = (now - self._dynamicBandwidthNoLimitTime)
							if (delta >= 5):
								# Use 100%
								logger.info(u"No other traffic detected, resetting dynamically limited bandwidth, using 100%")
								bwlimit = self._dynamicBandwidthLimit = 0.0
								self._bandwidthSleepTime = 0
								self._lastUnlimitedSpeed = 0
						else:
							self._dynamicBandwidthNoLimitTime = now
					else:
						self._dynamicBandwidthNoLimitTime = None
				else:
					if (usage <= 0.90):
						self._dynamicBandwidthNoLimitTime = None
						if self._dynamicBandwidthLimitTime:
							delta = (now - self._dynamicBandwidthLimitTime)
							if (delta >= 1.0):
								# Use 5% only
								self._lastUnlimitedSpeed = self._averageSpeed
								bwlimit = self._dynamicBandwidthLimit = self._averageSpeed*0.05
								logger.info(u"Other traffic detected, dynamically limiting bandwidth to 5%% of last average to %0.2f kByte/s" \
									% (bwlimit/1024))
								# For faster limiting:
								self._bandwidthSleepTime = 0.1
						else:
							self._dynamicBandwidthLimitTime = now
					else:
						self._dynamicBandwidthLimitTime = None
		
		if self._maxBandwidth and ((bwlimit == 0) or (bwlimit > self._maxBandwidth)):
			bwlimit = float(self._maxBandwidth)
		
		if (bwlimit == 0):
			return
		
		if (self._averageSpeed > bwlimit):
			# To fast
			factor = float(self._averageSpeed)/float(bwlimit)
			logger.debug2(u"Transfer speed %0.2f kByte/s is to fast, limit: %0.2f kByte/s, factor: %0.5f" \
				% ((self._averageSpeed/1024), (bwlimit/1024), factor))
			self._bandwidthSleepTime += (0.003 * (factor*factor))
			
			if (self._bandwidthSleepTime <= 0.0):
				self._bandwidthSleepTime = 0.0001
			#elif (self._bandwidthSleepTime > 0.5):
			#	self._bandwidthSleepTime = 0.5
			elif (self._bandwidthSleepTime > 0.4):
				self._bandwidthSleepTime = 0.4
		else:
			# To slow
			factor = float(bwlimit)/float(self._averageSpeed)
			logger.debug2(u"Transfer speed %0.2f kByte/s is to slow, limit: %0.2f kByte/s, factor: %0.5f" \
				% ((self._averageSpeed/1024), (bwlimit/1024), factor))
			
			self._bandwidthSleepTime -= (0.001 * (factor*factor))
			if (self._bandwidthSleepTime <= 0.0):
				self._bandwidthSleepTime = 0
			
		if (self._bandwidthSleepTime > 0):
			logger.debug2(u"Sleeping %f seconds to correct bandwidth" % self._bandwidthSleepTime)
			time.sleep(self._bandwidthSleepTime)
	
	def _transferDown(self, src, dst, progressSubject=None):
		self._transfer('in', src, dst, progressSubject)
		
	def _transferUp(self, src, dst, progressSubject=None):
		self._transfer('out', src, dst, progressSubject)
	
	
	def _transfer(self, transferDirection, src, dst, progressSubject=None):
		self._transferDirection = transferDirection
		bytesTransfered = 0
		lastBytes = 0
		lastAverageBytes = 0
		lastTime = lastAverageTime = transferStartTime = time.time()
		buf = True
		if not hasattr(self, '_bufferSize'):
			self._bufferSize = 4092
		self._averageSpeed = 0.0
		self._currentSpeed = 0.0
		
		while(buf):
			buf = src.read(self._bufferSize)
			read = len(buf)
			if (read > 0):
				lastAverageBytes += read
				lastBytes += read
				bytesTransfered += read
				if isinstance(dst, httplib.HTTPConnection) or isinstance(dst, httplib.HTTPSConnection):
					dst.send(buf)
				else:
					dst.write(buf)
				
				if progressSubject:
					progressSubject.addToState(read)
				
				now = time.time()
				
				delta = (now-lastTime)
				if (delta >= 1):
					self._currentSpeed = lastBytes/delta
					lastBytes = 0
					lastTime = now
				delta = (now-lastAverageTime)
				if (delta > 2):
					self._averageSpeed = lastAverageBytes/delta
					lastAverageTime = time.time() - 1
					lastAverageBytes = self._averageSpeed
					if (self._averageSpeed > 1000000):
						self._bufferSize = 131072
					
				if (bytesTransfered > self._bufferSize) and (self._maxBandwidth or self._dynamicBandwidth):
					self._sleepForBandwidth()
		
		transferTime = time.time() - transferStartTime
		if (transferTime == 0):
			transferTime = 0.0000001
		logger.info( u"Transfered %0.2f kByte in %0.2f minutes, average speed was %0.2f kByte/s" % \
			( (float(bytesTransfered)/1024), (float(transferTime)/60), (float(bytesTransfered)/transferTime)/1024) )
	
	def setMaxBandwidth(self, maxBandwidth):
		''' maxBandwidth in byte/s'''
		self._maxBandwidth = forceInt(maxBandwidth)
		if (self._maxBandwidth < 0):
			self._maxBandwidth = 0
	
	def _preProcessPath(self, path):
		return path
	
	def content(self, source='', recursive=False):
		raise RepositoryError(u"Not implemented")
	
	def listdir(self, source=''):
		result = []
		for c in self.content(source, recursive=False):
			result.append(c['name'])
		return result
	
	def getCountAndSize(self, source=''):
		source = forceUnicode(source)
		(count, size) = (0, 0)
		for entry in self.content(source, recursive = True):
			if (entry.get('type', '') == 'file'):
				count += 1
				size += entry.get('size', 0)
		return (count, size)
	
	def fileInfo(self, source):
		source = forceUnicode(source)
		info = {}
		try:
			parts = source.split('/')
			dirname = u'/'.join(parts[:-1])
			filename = parts[-1]
			if not filename:
				return {'name': dirname.split('/')[:-1], 'path': dirname.split('/')[:-1], 'type': 'dir', 'size': long(0)}
			for c in self.content(dirname):
				if (c['name'] == filename):
					info = c
					return info
			raise Exception(u'File not found')
		except Exception, e:
			#logger.logException(e)
			raise RepositoryError(u"Failed to get file info for '%s': %s" % (source, e))
		
	def exists(self, source):
		try:
			self.fileInfo(source)
		except:
			return False
		return True
	
	def isfile(self, source):
		try:
			info = self.fileInfo(source)
			return (info.get('type', '') == 'file')
		except:
			return False
	
	def isdir(self, source):
		try:
			info = self.fileInfo(source)
			return (info.get('type', '') == 'dir')
		except:
			return False
	
	def copy(self, source, destination, fileProgressSubject=None, overallProgressSubject=None, currentProgressSubject=None):
		#for hook in hooks:
		#	(source, destination, overallProgressSubject) = hook.pre_copy(source, destination, overallProgressSubject)
		
		'''
		source = file,  destination = file              => overwrite destination
		source = file,  destination = dir               => copy into destination
		source = file,  destination = not existent      => create destination directories, copy source to destination
		source = dir,   destination = file              => error
		source = dir,   destination = dir               => copy source dir into destination
		source = dir,   destination = not existent      => create destination, copy content of source into destination
		source = dir/*, destination = dir/not existent  => create destination if not exists, copy content of source into destination
		'''
		source = forceFilename(source)
		destination = forceFilename(destination)
		
		copySrcContent = False
		
		if source.endswith('/*.*') or source.endswith('\\*.*'):
			source = source[:-4]
			copySrcContent = True
			
		elif source.endswith('/*') or source.endswith('\\*'):
			source = source[:-2]
			copySrcContent = True
		
		if copySrcContent and not self.isdir(source):
			raise Exception(u"Source directory '%s' not found" % source)
		
		logger.info(u"Copying from '%s' to '%s'" % (source, destination))
		(totalFiles, size) = (0, 0)
		if overallProgressSubject:
			overallProgressSubject.reset()
			(totalFiles, size) = self.getCountAndSize(source)
			overallProgressSubject.setEnd(size)
		
		try:
			info = self.fileInfo(source)
			if (info.get('type') == 'file'):
				destinationFile = destination
				if not os.path.exists(destination):
					os.makedirs(destination)
					destinationFile = os.path.join(destination, info['name'])
				elif os.path.isdir(destination):
					destinationFile = os.path.join(destination, info['name'])
				
				if overallProgressSubject:
					sizeString = "%d Byte" % info['size']
					if (info['size'] > 1024*1024):
						sizeString = "%0.2f MByte" % ( float(info['size'])/(1024*1024) )
					elif (info['size'] > 1024):
						sizeString = "%0.2f kByte" % ( float(info['size'])/(1024) )
					overallProgressSubject.setMessage(u"[1/1] %s (%s)" % (info['name'], sizeString ) )
				try:
					self.download(source, destinationFile, currentProgressSubject)
				except OSError, e:
					if (e.errno != 1):
						raise
					# Operation not permitted
					logger.debug(e)
				if overallProgressSubject:
					overallProgressSubject.addToState(info['size'])
				
			elif (info.get('type') == 'dir'):
				if not os.path.exists(destination):
					os.makedirs(destination)
				elif os.path.isfile(destination):
					raise Exception(u"Cannot copy directory '%s' into file '%s'" % (source, destination))
				elif os.path.isdir(destination):
					if not copySrcContent:
						destination = os.path.join(destination, info['name'])
				content = self.content(source, recursive = True)
				fileCount = 0
				for c in content:
					if (c.get('type') == 'dir'):
						path = [ destination ]
						path.extend(c['path'].split('/'))
						targetDir = os.path.join(*path)
						if not targetDir:
							raise Exception(u"Bad target directory '%s'" % targetDir)
						if not os.path.isdir(targetDir):
							os.makedirs(targetDir)
					elif (c.get('type') == 'file'):
						fileCount += 1
						if overallProgressSubject:
							countLen = len(str(totalFiles))
							countLenFormat = '%' + str(countLen) + 's'
							sizeString = "%d Byte" % c['size']
							if (c['size'] > 1024*1024):
								sizeString = "%0.2f MByte" % ( float(c['size'])/(1024*1024) )
							elif (c['size'] > 1024):
								sizeString = "%0.2f kByte" % ( float(c['size'])/(1024) )
							overallProgressSubject.setMessage(u"[%s/%s] %s (%s)" \
									% (countLenFormat % fileCount, totalFiles, c['name'], sizeString ) )
						
						path = [ destination ]
						path.extend(c['path'].split('/')[:-1])
						targetDir = os.path.join(*path)
						if not targetDir:
							raise Exception(u"Bad target directory '%s'" % targetDir)
						if targetDir and not os.path.isdir(targetDir):
							os.makedirs(targetDir)
						self.download(u'/'.join((source, c['path'])), os.path.join(targetDir, c['name']), currentProgressSubject)
						
						if overallProgressSubject:
							overallProgressSubject.addToState(c['size'])
			else:
				raise Exception(u"Failed to copy: unknown source type '%s'" % source)
			logger.info(u'Copy done')
			if overallProgressSubject:
				overallProgressSubject.setState(size)
		except Exception, e:
			raise
		#	for hook in hooks:
		#		hook.error_copy(source, destination, overallProgressSubject, e)
		#
		#for hook in hooks:
		#	hook.post_copy(source, destination, overallProgressSubject)
	
	def upload(self, source, destination):
		raise RepositoryError(u"Not implemented")
	
	def download(self, source, destination, progressObserver=None):
		raise RepositoryError(u"Not implemented")
	
	def delete(self, destination):
		raise RepositoryError(u"Not implemented")
	
	def makeDirectory(self, destination):
		raise RepositoryError(u"Not implemented")
	
class FileRepository(Repository):
	def __init__(self, url, username=u'', password=u'', maxBandwidth=0, dynamicBandwidth=False, application=''):
		Repository.__init__(self, url, username, password, maxBandwidth, False, application)
		
		match = re.search('^file://(/[^/]+.*)$', self._url)
		if not match:
			raise RepositoryError(u"Bad file url: '%s'" % self._url)
		self._path = match.group(1)
		
	def _preProcessPath(self, path):
		path = forceUnicode(path)
		if path.startswith('/'):
			path = path[1:]
		if path.endswith('/'):
			path = path[:-1]
		return self._path + u'/' + path
	
	def exists(self, source):
		return os.path.exists(self._preProcessPath(source))
		
	def isfile(self, source):
		return os.path.isfile(self._preProcessPath(source))
	
	def isdir(self, source):
		return os.path.isdir(self._preProcessPath(source))
	
	def content(self, source='', recursive=False):
		source = self._preProcessPath(source)
		
		content = []
		srcLen = len(source)
		def _recurse(path, content):
			path = os.path.abspath(forceFilename(path))
			for entry in os.listdir(path):
				try:
					info = { 'name': entry, 'size': long(0), 'type': 'file' }
					entry = os.path.join(path, entry)
					info['path'] = entry[srcLen:]
					size = 0
					if os.path.islink(entry):
						pass
					elif os.path.isfile(entry):
						info['size'] = os.path.getsize(entry)
						content.append(info)
					elif os.path.isdir(entry):
						info['type'] = 'dir'
						content.append(info)
						if recursive:
							_recurse(path = entry, content = content)
				except Exception, e:
					logger.error(e)
			return content
		return _recurse(path = source, content = content)
	
	def download(self, source, destination, progressSubject=None):
		size = self.fileInfo(source)['size']
		source = self._preProcessPath(source)
		destination = forceUnicode(destination)
		
		logger.debug(u"Length of binary data to download: %d bytes" % size)
		
		if progressSubject: progressSubject.setEnd(size)
		
		(src, dst) = (None, None)
		try:
			src = open(source, 'rb')
			dst = open(destination, 'wb')
			self._transferDown(src, dst, progressSubject)
			src.close()
			dst.close()
		except Exception, e:
			if src: src.close()
			if dst: dst.close()
			raise RepositoryError(u"Failed to download '%s' to '%s': %s" \
						% (source, destination, e))
	
	def upload(self, source, destination, progressSubject=None):
		source = forceUnicode(source)
		destination = self._preProcessPath(destination)
		
		fs = os.stat(source)
		size = fs[stat.ST_SIZE]
		logger.debug(u"Length of binary data to upload: %d" % size)
		
		if progressSubject: progressSubject.setEnd(size)
		
		(src, dst) = (None, None)
		try:
			src = open(source, 'rb')
			dst = open(destination, 'wb')
			self._transferUp(src, dst, progressSubject)
			src.close()
			dst.close()
		except Exception, e:
			if src: src.close()
			if dst: dst.close()
			raise RepositoryError(u"Failed to upload '%s' to '%s': %s" \
						% (source, destination, e))
	
	def delete(self, destination):
		destination = self._preProcessPath(destination)
		os.unlink(destination)
	
	def makeDirectory(self, destination):
		destination = self._preProcessPath(destination)
		if not os.path.isdir(destination):
			os.mkdir(destination)
		

class HTTPRepository(Repository):
	def __init__(self, url, username=u'', password=u'', maxBandwidth=0, dynamicBandwidth=False, application='', proxy = None):
		Repository.__init__(self, url, username, password, maxBandwidth, dynamicBandwidth, application)
		self._connectTimeout = 30
		self._port = 80
		self._path = u'/'
		
		parts = self._url.split('/')
		if (len(parts) < 3) or parts[0].lower() not in ('http:', 'https:', 'webdav:', 'webdavs:'):
			raise RepositoryError(u"Bad http url: '%s'" % self._url)
		
		self._protocol = parts[0].lower()[:-1]
		if self._protocol.endswith('s'):
			self._port = 443
		
		self._host = parts[2]
		if (len(parts) > 3):
			self._path += u'/'.join(parts[3:])
		
		if (self._host.find('@') != -1):
			(username, self._host) = self._host.split('@', 1)
			password = ''
			if (username.find(':') != -1):
				(username, password) = username.split(':', 1)
			if not self._username and username: self._username = username
			if not self._password and password: self._password = password
		
		if (self._host.find(':') != -1):
			(self._host, self._port) = self._host.split(':', 1)
			self._port = forceInt(self._port)
		
		self._connection = None
		self._cookie = ''
		self._username = forceUnicode(self._username)
		self._password = forceUnicode(self._password)
		
		auth = u'%s:%s' % (self._username, self._password)
		self._auth = 'Basic '+ base64.encodestring(auth.encode('latin-1')).strip()
		self._proxy = None
		
		if proxy:
			self._proxy = proxy
			self._auth = None
			match = re.search('^(https?)://([^:]+:*[^:]+):(\d+)$', proxy)
			if not match:
				raise RepositoryError(u"Bad proxy url: '%s'" % proxy)
			proxyProtocol = match.group(1)
			proxyHost = match.group(2)
			if (self._host.find('@') != -1):
				(proxyUsername, proxyHost) = proxyHost.split('@', 1)
				proxyPassword = ''
				if (proxyUsername.find(':') != -1):
					(proxyUsername, proxyPassword) = proxyUsername.split(':', 1)
				auth = u'%s:%s' % (proxyUsername, proxyPassword)
				self._auth = 'Basic '+ base64.encodestring(auth.encode('latin-1')).strip()
			proxyPort = forceInt(match.group(3))
			if self._username and self._password:
				self._url = u'%s://%s:%s@%s:%d%s' % (self._protocol, self._username, self._password, self._host, self._port, self._path)
			else:
				self._url = u'%s://%s:%d%s' % (self._protocol, self._host, self._port, self._path)
			self._protocol = proxyProtocol
			self._host = proxyHost
			self._port = proxyPort
		
	def _preProcessPath(self, path):
		path = forceUnicode(path)
		if path.startswith('/'):
			path = path[1:]
		if self._proxy:
			if self._url.endswith('/'):
				path = self._url + path
			else:
				path = self._url + u'/' + path
		else:
			path = self._path + u'/' + path
		if path.endswith('/'):
			path = path[:-1]
		return urllib.quote(path.encode('utf-8'))
		
	def _connect(self):
		logger.debug(u"HTTPRepository _connect()")
		
		if self._protocol.endswith('s'):
			logger.info(u"Opening https connection to %s:%s" % (self._host, self._port))
			self._connection = httplib.HTTPSConnection(self._host, self._port)
			non_blocking_connect_https(self._connection, self._connectTimeout)
		else:
			logger.info(u"Opening http connection to %s:%s" % (self._host, self._port))
			self._connection = httplib.HTTPConnection(self._host, self._port)
			non_blocking_connect_http(self._connection, self._connectTimeout)
		
		self._connection.connect()
		logger.info(u"Successfully connected to '%s:%s'" % (self._host, self._port))
	
	def download(self, source, destination, progressSubject=None):
		destination = forceUnicode(destination)
		#try:
		#	size = self.fileInfo(source)['size']
		#except:
		#	pass
		source = self._preProcessPath(source)
		
		dst = None
		try:
			if not self._connection:
				self._connect()
			self._connection.putrequest('GET', source)
			self._connection.putheader('user-agent', self._application)
			if self._cookie:
				# Add cookie to header
				self._connection.putheader('cookie', self._cookie)
			if self._auth:
				self._connection.putheader('authorization', self._auth)
			self._connection.endheaders()
			
			response = self._connection.getresponse()
			if (response.status != responsecode.OK):
				raise Exception(response.status)
			
			size = forceInt(response.getheader('content-length', 0))
			logger.debug(u"Length of binary data to download: %d bytes" % size)
			
			if progressSubject: progressSubject.setEnd(size)
			
			dst = open(destination, 'wb')
			self._transferDown(response, dst, progressSubject)
			dst.close()
			
		except Exception, e:
			logger.logException(e)
			#if self._connection: self._connection.close()
			if dst: dst.close()
			raise RepositoryError(u"Failed to download '%s' to '%s': %s" % (source, destination, e))
		logger.debug2(u"HTTP download done")
	
class WebDAVRepository(HTTPRepository):
	def __init__(self, url, username=u'', password=u'', maxBandwidth=0, dynamicBandwidth=False, application=''):
		HTTPRepository.__init__(self, url, username, password, maxBandwidth, dynamicBandwidth, application)
		parts = self._url.split('/')
		if (len(parts) < 3) or parts[0].lower() not in ('webdav:', 'webdavs:'):
			raise RepositoryError(u"Bad http url: '%s'" % self._url)
		self._contentCache = {}
		
	def _connect(self):
		HTTPRepository._connect(self)
		
		#self._connection.putrequest('PROPFIND', self._preProcessPath('/'))
		#self._connection.putheader('user-agent', self._application)
		#if self._cookie:
		#	# Add cookie to header
		#	self._connection.putheader('cookie', self._cookie)
		#if self._auth:
		#	self._connection.putheader('authorization', self._auth)
		#self._connection.putheader('depth', '0')
		#self._connection.endheaders()
		#
		#response = self._connection.getresponse()
		#if (response.status != responsecode.MULTI_STATUS):
		#	raise RepositoryError(u"Failed to connect to '%s://%s:%s': %s" \
		#		% (self._protocol, self._host, self._port, response.status))
		## We have to read the response!
		#response.read()
		#
		## Get cookie from header
		#cookie = response.getheader('set-cookie', None)
		#if cookie:
		#	# Store cookie
		#	self._cookie = cookie.split(';')[0].strip()
	
	def content(self, source='', recursive=False):
		source = forceUnicode(source)
		
		source = self._preProcessPath(source)
		if not source.endswith('/'):
			source += '/'
		
		if recursive and self._contentCache.has_key(source):
			return self._contentCache[source]
		
		content = []
		if not self._connection:
			self._connect()
		
		self._connection.putrequest('PROPFIND', source)
		depth = '1'
		if recursive:
			depth = 'infinity'
		self._connection.putheader('depth', depth)
		if self._cookie:
			# Add cookie to header
			self._connection.putheader('cookie', self._cookie)
		self._connection.putheader('user-agent', self._application)
		if self._auth:
			self._connection.putheader('authorization', self._auth)
		self._connection.endheaders()
		
		response = self._connection.getresponse()
		if (response.status != responsecode.MULTI_STATUS):
			raise RepositoryError(u"Failed to list dir '%s': %s" % (source, response.status))
		
		encoding = 'utf-8'
		contentType = response.getheader('content-type', '').lower()
		for part in contentType.split(';'):
			if (part.find('charset=') != -1):
				encoding = part.split('=')[1].replace('"', '').strip()
		
		msr = davxml.WebDAVDocument.fromString(response.read())
		if not msr.root_element.children[0].childOfType(davxml.PropertyStatus).childOfType(davxml.PropertyContainer).childOfType(davxml.ResourceType).children:
			raise RepositoryError(u"Not a directory: '%s'" % source)
		
		srcLen = len(source)
		for child in msr.root_element.children[1:]:
			pContainer = child.childOfType(davxml.PropertyStatus).childOfType(davxml.PropertyContainer)
			info = { 'size': long(0), 'type': 'file' }
			info['path'] = unicode(urllib.unquote(child.childOfType(davxml.HRef).children[0].data), encoding)[srcLen:]
			info['name'] = unicode(pContainer.childOfType(davxml.DisplayName).children[0].data, encoding)
			if (str(pContainer.childOfType(davxml.GETContentLength)) != 'None'):
				info['size'] = long( str(pContainer.childOfType(davxml.GETContentLength)) )
			if pContainer.childOfType(davxml.ResourceType).children:
				info['type'] = 'dir'
				if info['path'].endswith('/'):
					info['path'] = info['path'][:-1]
			content.append(info)
		
		if recursive:
			self._contentCache[source] = content
		return content
	
	def upload(self, source, destination, progressSubject=None):
		source = forceUnicode(source)
		destination = self._preProcessPath(destination)
		
		fs = os.stat(source)
		size = fs[stat.ST_SIZE]
		logger.debug(u"Length of binary data to upload: %d" % size)
		
		if progressSubject: progressSubject.setEnd(size)
		
		src = None
		try:
			if not self._connection:
				self._connect()
			self._connection.putrequest('PUT', destination)
			self._connection.putheader('user-agent', self._application)
			if self._cookie:
				# Add cookie to header
				self._connection.putheader('cookie', self._cookie)
			if self._auth:
				self._connection.putheader('authorization', self._auth)
			self._connection.putheader('content-length', size)
			self._connection.endheaders()
			
			src = open(source, 'rb')
			self._transferUp(src, self._connection, progressSubject)
			src.close()
			
			response = self._connection.getresponse()
			if (response.status != responsecode.CREATED) and (response.status != responsecode.NO_CONTENT):
				raise Exception(response.status)
			# We have to read the response!
			response.read()
		except Exception, e:
			logger.logException(e)
			if src: src.close()
			raise RepositoryError(u"Failed to upload '%s' to '%s': %s" % (source, destination, e))
		logger.debug2(u"WebDAV upload done")
	
	def delete(self, destination):
		if not self._connection:
			self._connect()
		
		destination = self._preProcessPath(destination)
		
		self._connection.putrequest('DELETE', destination)
		self._connection.putheader('user-agent', self._application)
		if self._cookie:
			# Add cookie to header
			self._connection.putheader('cookie', self._cookie)
		if self._auth:
			self._connection.putheader('authorization', self._auth)
		self._connection.endheaders()
		
		response = self._connection.getresponse()
		if (response.status != responsecode.NO_CONTENT):
			raise RepositoryError(u"Failed to delete '%s': %s" % (destination, response.status))
		# We have to read the response!
		response.read()

class DepotToLocalDirectorySychronizer(object):
	def __init__(self, sourceDepot, destinationDirectory, productIds=[], maxBandwidth=0, dynamicBandwidth=False):
		self._sourceDepot          = sourceDepot
		self._destinationDirectory = forceUnicode(destinationDirectory)
		self._productIds           = forceUnicodeList(productIds)
		self._maxBandwidth         = forceInt(maxBandwidth)
		self._dynamicBandwidth     = forceBool(dynamicBandwidth)
		if not os.path.isdir(self._destinationDirectory):
			os.mkdir(self._destinationDirectory)
	
	def _synchronizeDirectories(self, source, destination, progressSubject=None):
		source = forceUnicode(source)
		destination = forceUnicode(destination)
		logger.debug(u"   Syncing directory %s to %s" % (source, destination))
		if not os.path.isdir(destination):
			os.mkdir(destination)
		
		for f in os.listdir(destination):
			relSource = (source + u'/' + f).split(u'/', 1)[1]
			if (relSource == self._productId + u'.files'):
				continue
			if self._fileInfo.has_key(relSource):
				continue
			
			logger.info(u"      Deleting '%s'" % relSource)
			path = os.path.join(destination, f)
			if os.path.isdir(path) and not os.path.islink(path):
				shutil.rmtree(path)
			else:
				os.remove(path)
			
		for f in self._sourceDepot.content(source):
			source = forceUnicode(source)
			(s, d) = (source + u'/' + f['name'], os.path.join(destination, f['name']))
			relSource = s.split(u'/', 1)[1]
			if not self._fileInfo.has_key(relSource):
				continue
			if (f['type'] == 'dir'):
				self._synchronizeDirectories(s, d, progressSubject)
			else:
				bytes = 0
				logger.debug(u"      Syncing %s: %s" % (relSource, self._fileInfo[relSource]))
				if (self._fileInfo[relSource]['type'] == 'l'):
					self._linkFiles[relSource] = self._fileInfo[relSource]['target']
					continue
				elif (self._fileInfo[relSource]['type'] == 'f'):
					bytes = int(self._fileInfo[relSource]['size'])
					if os.path.exists(d):
						md5s = md5sum(d)
						logger.debug(u"      Destination file '%s' already exists (size: %s, md5sum: %s)" % (d, bytes, md5s))
						if (os.path.getsize(d) == bytes) and (md5s == self._fileInfo[relSource]['md5sum']):
							if progressSubject: progressSubject.addToState(bytes)
							continue
				logger.info(u"      Downloading file '%s'" % f['name'])
				if progressSubject: progressSubject.setMessage( _(u"Downloading file '%s'") % f['name'] )
				self._sourceDepot.download(s, d)
				if progressSubject: progressSubject.addToState(bytes)
				
	def synchronize(self, productProgressObserver=None, overallProgressObserver=None):
		
		if not self._productIds:
			logger.info(u"Getting product dirs of depot '%s'" % self._sourceDepot)
			for c in self._sourceDepot.content():
				self._productIds.append(c['name'])
		
		overallProgressSubject = ProgressSubject(id = 'sync_products_overall', type = 'product_sync', end = len(self._productIds), fireAlways = True)
		overallProgressSubject.setMessage( _(u'Synchronizing products') )
		if overallProgressObserver: overallProgressSubject.attachObserver(overallProgressObserver)
		
		for self._productId in self._productIds:
			productProgressSubject = ProgressSubject(id = 'sync_product_' + self._productId, type = 'product_sync', fireAlways = True)
			productProgressSubject.setMessage( _(u"Synchronizing product %s") % self._productId )
			if productProgressObserver: productProgressSubject.attachObserver(productProgressObserver)
			packageContentFile = None
			
			try:
				self._linkFiles = {}
				logger.notice(u"Syncing product %s of depot %s with local directory %s" \
						% (self._productId, self._sourceDepot, self._destinationDirectory))
				
				productDestinationDirectory = os.path.join(self._destinationDirectory, self._productId)
				if not os.path.isdir(productDestinationDirectory):
					os.mkdir(productDestinationDirectory)
				
				logger.info(u"Downloading package content file")
				packageContentFile = os.path.join(productDestinationDirectory, u'%s.files' % self._productId)
				self._sourceDepot.download(u'%s/%s.files' % (self._productId, self._productId), packageContentFile)
				self._fileInfo = PackageContentFile(packageContentFile).parse()
				
				bytes = 0
				for value in self._fileInfo.values():
					if value.has_key('size'):
						bytes += int(value['size'])
				productProgressSubject.setMessage( _(u"Synchronizing product %s (%.2f kByte)") % (self._productId, (bytes/1024)) )
				productProgressSubject.setEnd(bytes)
				
				self._synchronizeDirectories(self._productId, productDestinationDirectory, productProgressSubject)
				
				fs = self._linkFiles.keys()
				fs.sort()
				for f in fs:
					t = self._linkFiles[f]
					cwd = os.getcwd()
					os.chdir(productDestinationDirectory)
					try:
						if os.path.exists(f):
							if os.path.isdir(f) and not os.path.islink(f):
								shutil.rmtree(f)
							else:
								os.remove(f)
						if (os.name == 'posix'):
							parts = len(f.split('/'))
							parts -= len(t.split('/'))
							for i in range(parts):
								t = os.path.join('..', t)
							logger.info(u"Symlink '%s' to '%s'" % (f, t))
							os.symlink(t, f)
						else:
							t = os.path.join(productDestinationDirectory, t)
							f = os.path.join(productDestinationDirectory, f)
							logger.info(u"Copying '%s' to '%s'" % (t, f))
							if os.path.isdir(t):
								shutil.copytree(t, f)
							else:
								shutil.copyfile(t, f)
					finally:
						os.chdir(cwd)
			except Exception, e:
				productProgressSubject.setMessage( _(u"Failed to sync product %s: %s") % (self._productId, e) )
				if packageContentFile and os.path.exists(packageContentFile):
					os.unlink(packageContentFile)
				raise
				
			overallProgressSubject.addToState(1)
			if productProgressObserver: productProgressSubject.detachObserver(productProgressObserver)
			
		if overallProgressObserver: overallProgressSubject.detachObserver(overallProgressObserver)



if (__name__ == "__main__"):
	#logger.setConsoleLevel(LOG_DEBUG2)
	
	tempFile = '/tmp/testfile.bin'
	tempDir = '/tmp/testdir'
	tempDir2 = '/tmp/testdir2'
	if os.path.exists(tempFile):
		os.unlink(tempFile)
	if os.path.exists(tempDir):
		shutil.rmtree(tempDir)
	if os.path.exists(tempDir2):
		shutil.rmtree(tempDir2)
	
	#rep = HTTPRepository(url = u'http://download.uib.de:80', username = u'', password = u'')
	#rep.download(u'press-infos/logos/opsi/opsi-Logo_4c.pdf', tempFile, progressSubject=None)
	#os.unlink(tempFile)
	#
	#rep = HTTPRepository(url = u'http://download.uib.de', username = u'', password = u'')
	#rep.download(u'press-infos/logos/opsi/opsi-Logo_4c.pdf', tempFile, progressSubject=None)
	#os.unlink(tempFile)
	#
	#rep = HTTPRepository(url = u'http://download.uib.de:80', username = u'', password = u'', proxy="http://192.168.1.254:3128")
	#rep.download(u'press-infos/logos/opsi/opsi-Logo_4c.pdf', tempFile, progressSubject=None)
	#os.unlink(tempFile)
	#
	#rep = HTTPRepository(url = u'http://download.uib.de', username = u'', password = u'', proxy="http://192.168.1.254:3128")
	#rep.download(u'press-infos/logos/opsi/opsi-Logo_4c.pdf', tempFile, progressSubject=None)
	#os.unlink(tempFile)
	#
	#rep = HTTPRepository(url = u'https://forum.opsi.org:443', username = u'', password = u'')
	#rep.download(u'/index.php', tempFile, progressSubject=None)
	#os.unlink(tempFile)
	
	#rep = WebDAVRepository(url = u'webdavs://192.168.1.14:4447/repository', username = u'autotest001.uib.local', password = u'b61455728859cfc9988a3d9f3e2343b3')
	#rep.download(u'xpconfig_2.6-1.opsi', tempFile, progressSubject=None)
	#for c in rep.content():
	#	print c
	#print rep.getCountAndSize()
	#print rep.exists('shutdownwanted_1.0-2.opsi')
	#print rep.exists('notthere')
	#rep.copy('shutdownwanted_1.0-2.opsi', tempDir)
	#shutil.rmtree(tempDir)
	#os.makedirs(tempDir)
	#rep.copy('shutdownwanted_1.0-2.opsi', tempDir)
	#rep.copy('shutdownwanted_1.0-2.opsi', tempDir)
	#
	#shutil.rmtree(tempDir)
	
	#rep = WebDAVRepository(url = u'webdavs://192.168.1.14:4447/depot', username = u'autotest001.uib.local', password = u'b61455728859cfc9988a3d9f3e2343b3')
	#for c in rep.content('winvista-x64/installfiles', recursive=True):
	#	print c
	#rep.copy(source = 'winvista-x64/installfiles', destination = tempDir)
	
	#from UI import UIFactory
	#ui = UIFactory()
	#from Message import ProgressObserver
	#overallProgressSubject = ProgressSubject(id = u'copy_overall', title = u'Copy test')
	#currentProgressSubject = ProgressSubject(id = u'copy_current', title = u'Copy test')
	##class SimpleProgressObserver(ProgressObserver):
	##	def messageChanged(self, subject, message):
	##		print u"%s" % message
	##	
	##	def progressChanged(self, subject, state, percent, timeSpend, timeLeft, speed):
	##		print u"state: %s, percent: %0.2f%%, timeSpend: %0.2fs, timeLeft: %0.2fs, speed: %0.2f" \
	##			% (state, percent, timeSpend, timeLeft, speed)
	##progressSubject.attachObserver(SimpleProgressObserver())
	##copyBox = ui.createCopyProgressBox(width = 120, height = 20, title = u'Copy', text = u'')
	#copyBox = ui.createCopyDualProgressBox(width = 120, height = 20, title = u'Copy', text = u'')
	#copyBox.show()
	#copyBox.setOverallProgressSubject(overallProgressSubject)
	#copyBox.setCurrentProgressSubject(currentProgressSubject)
	
	#progressSubject.attachObserver(copyBox)
	
	overallProgressSubject = None
	currentProgressSubject = None
	#rep = WebDAVRepository(url = u'webdavs://192.168.1.14:4447/depot', username = u'autotest001.uib.local', password = u'b61455728859cfc9988a3d9f3e2343b3')
	#for c in rep.content('swaudit', recursive=True):
	#	print c
	
	rep = WebDAVRepository(url = u'webdavs://192.168.1.14:4447/depot/swaudit', username = u'autotest001.uib.local', password = u'b61455728859cfc9988a3d9f3e2343b3')
	#for c in rep.content('swaudit', recursive=True):
	#	print c
	print rep.listdir()
	rep.copy(source = '/*', destination = tempDir, overallProgressSubject = overallProgressSubject, currentProgressSubject = currentProgressSubject)
	
	time.sleep(1)
	
	#overallProgressSubject.reset()
	#currentProgressSubject.reset()
	rep = FileRepository(url = u'file://%s' % tempDir)
	#for c in rep.content('', recursive=True):
	#	print c
	print rep.exists('/MSVCR71.dll')
	print rep.isdir('lib')
	print rep.isfile('äää.txt')
	print rep.listdir()
	rep.copy(source = '/*', destination = tempDir2, overallProgressSubject = overallProgressSubject, currentProgressSubject = currentProgressSubject)
	
	
	#ui.exit()
	#rep = FileRepository(url = u'file:///tmp')
	#for c in rep.content('', recursive=True):
	#	print c
	
	#rep = HTTPRepository(url = u'webdav://download.uib.de:80/opsi3.4', dynamicBandwidth = True)
	#rep.download(u'opsi3.4-client-boot-cd_20091028.iso', '/tmp/opsi3.4-client-boot-cd_20091028.iso', progressSubject=None)
	#sourceDepot = WebDAVRepository(url = u'webdavs://192.168.1.14:4447/opsi-depot', username = u'autotest001.uib.local', password = u'b61455728859cfc9988a3d9f3e2343b3')
	#dtlds = DepotToLocalDirectorySychronizer(sourceDepot, destinationDirectory = '/tmp/depot', productIds=['preloginloader', 'opsi-winst', 'thunderbird'], maxBandwidth=0, dynamicBandwidth=False)
	#dtlds.synchronize()






















