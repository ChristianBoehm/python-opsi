# -*- coding: utf-8 -*-

# This module is part of the desktop management solution opsi
# (open pc server integration) http://www.opsi.org

# Copyright (C) 2006-2019 uib GmbH <info@uib.de>
# http://www.uib.de/

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
General utility functions.

This module holds various utility functions for the work with opsi.
This includes functions for (de)serialisation, converting classes from
or to JSON, working with librsync and more.

:copyright:	uib GmbH <info@uib.de>
:author: Jan Schneider <j.schneider@uib.de>
:author: Niko Wenselowski <n.wenselowski@uib.de>
:license: GNU Affero General Public License version 3
"""

import base64
import binascii
import codecs
import ipaddress
try:
	# ujson is faster
	import ujson as json
except ModuleNotFoundError:
	import json
import os
import random
import re
import shutil
import socket
import struct
import sys
import time
import types
from collections import namedtuple
from hashlib import md5
from itertools import islice
from functools import lru_cache

try:
	# python3-pycryptodome installs into Cryptodome
	from Cryptodome.Cipher import Blowfish
	from Cryptodome.PublicKey import RSA
	from Cryptodome.Util.number import bytes_to_long
except ImportError:
	# PyCryptodome from pypi installs into Crypto
	from Crypto.Cipher import Blowfish
	from Crypto.PublicKey import RSA
	from Crypto.Util.number import bytes_to_long

from OPSI.Logger import Logger, LOG_DEBUG
from OPSI.Types import (forceBool, forceFilename, forceFqdn, forceInt,
						forceIPAddress, forceNetworkAddress, forceUnicode)

OPSIObject = None

try:
	import secrets  # Since Python 3.6
except ImportError:
	secrets = None

__all__ = (
	'BLOWFISH_IV', 'PickleString',
	'RANDOM_DEVICE', 'blowfishDecrypt', 'blowfishEncrypt',
	'chunk', 'compareVersions', 'decryptWithPrivateKeyFromPEMFile',
	'deserialize', 'encryptWithPublicKeyFromX509CertificatePEMFile',
	'findFiles', 'findFilesGenerator', 'formatFileSize', 'fromJson', 'generateOpsiHostKey',
	'getfqdn', 'ipAddressInNetwork', 'isRegularExpressionPattern',
	'md5sum', 'objectToBash', 'objectToBeautifiedText', 'objectToHtml',
	'randomString', 'removeDirectory', 'removeUnit',
	'replaceSpecialHTMLCharacters', 'serialize', 'timestamp', 'toJson'
)

logger = Logger()

BLOWFISH_IV = b"OPSI1234"
RANDOM_DEVICE = "/dev/urandom"
UNIT_REGEX = re.compile(r'^(\d+\.*\d*)\s*([\w]{0,4})$')
UNIT_REGEX = re.compile(r'^(\d+\.*\d*)\s*(\w{0,4})$')
_ACCEPTED_CHARACTERS = (
	"abcdefghijklmnopqrstuvwxyz"
	"ABCDEFGHIJKLMNOPQRSTUVWXYZ"
	"0123456789"
)

Version = namedtuple('Version', 'product package')


class CryptoError(ValueError):
	pass


class BlowfishError(CryptoError):
	pass


class PickleString(str):

	def __getstate__(self):
		return base64.standard_b64encode(self)

	def __setstate__(self, state):
		self = base64.standard_b64decode(state)


def deserialize(obj, preventObjectCreation=False):
	global OPSIObject
	if OPSIObject is None:
		import OPSI.Object as OPSIObject
	"""
	Deserialization of `obj`.

	This function will deserialize objects from JSON into opsi \
compatible objects.
	In case `obj` is a list contained elements are deserialized.
	In case `obj` is a dict the values are deserialized.

	In case `obj` is a dict and holds a key *type* and \
`preventObjectCreation` is `True` it will be tried to create an opsi \
object instance from it

	:type obj: object
	:type preventObjectCreation: bool
	"""
	if isinstance(obj, list):
		return [deserialize(element, preventObjectCreation=preventObjectCreation) for element in obj]
	elif isinstance(obj, dict):
		if not preventObjectCreation and 'type' in obj:
			try:
				objectClass = eval('OPSIObject.%s' % obj['type'])
				return objectClass.fromHash(obj)
			except Exception as error:
				logger.debug(u"Failed to get object from dict %s: %s", obj, forceUnicode(error))
				return obj
		else:
			return {
				key: deserialize(value, preventObjectCreation=preventObjectCreation)
				for key, value in obj.items()
			}
	else:
		return obj


def serialize(obj):
	"""
	Serialize `obj`.

	It will turn an object into a JSON-compatible format - consisting \
of strings, dicts, lists or numbers.

	:return: a JSON-compatible serialisation of the input.
	"""
	if isinstance(obj, str):
		return obj

	try:
		return obj.serialize()
	except AttributeError:
		if isinstance(obj, (list, set, types.GeneratorType)):
			return [serialize(tempObject) for tempObject in obj]
		elif isinstance(obj, dict):
			return {key: serialize(value) for key, value in obj.items()}

	return obj


def formatFileSize(sizeInBytes):
	if sizeInBytes < 1024:
		return '%i' % sizeInBytes
	elif sizeInBytes < 1048576:  # 1024**2
		return '%iK' % (sizeInBytes / 1024)
	elif sizeInBytes < 1073741824:  # 1024**3
		return '%iM' % (sizeInBytes / 1048576)
	elif sizeInBytes < 1099511627776:  # 1024**4
		return '%iG' % (sizeInBytes / 1073741824)
	else:
		return '%iT' % (sizeInBytes / 1099511627776)


def fromJson(obj, objectType=None, preventObjectCreation=False):
	if type(obj) is bytes:
		# Allow decoding errors (workaround for opsi-script bug)
		obj = obj.decode("utf-8", "replace")
	obj = json.loads(obj)
	if isinstance(obj, dict) and objectType:
		obj['type'] = objectType
	return deserialize(obj, preventObjectCreation=preventObjectCreation)


def toJson(obj, ensureAscii=False):
	return json.dumps(serialize(obj), ensure_ascii=ensureAscii)


def md5sum(filename):
	""" Returns the md5sum of the given file. """
	md5object = md5()

	with open(filename, 'rb') as fileToHash:
		for data in iter(lambda: fileToHash.read(524288), b''):
			md5object.update(data)

	return md5object.hexdigest()


def randomString(length, characters=_ACCEPTED_CHARACTERS):
	"""
	Generates a random string for a given length.

	:param characters: The characters to choose from. This defaults to 0-9a-Z.
	"""
	return forceUnicode(u''.join(random.choice(characters) for _ in range(length)))


def generateOpsiHostKey(forcePython=False):
	"""
	Generates an random opsi host key.

	On Python 3.5 or lower this will try to make use of an existing
	random device.
	As a fallback the generation is done in plain Python.

	:param forcePython: Force the usage of Python for host key generation.
	:rtype: str
	"""
	if secrets:
		return secrets.token_hex(16)

	if os.name == 'posix' and not forcePython:
		logger.debug2(u"Opening random device %s to generate opsi host key", RANDOM_DEVICE)
		with open(RANDOM_DEVICE, 'rb') as r:
			key = r.read(16)
		logger.debug2("Random device closed")
		key = binascii.hexlify(key)
		key = key.decode()
	else:
		logger.debug(u"Using python random module to generate opsi host key")
		key = randomString(32, "0123456789abcdef")

	return key


def timestamp(secs=0, dateOnly=False):
	''' Returns a timestamp of the current system time format: YYYY-mm-dd[ HH:MM:SS] '''
	if not secs:
		secs = time.time()
	if dateOnly:
		return time.strftime(u"%Y-%m-%d", time.localtime(secs))
	else:
		return time.strftime(u"%Y-%m-%d %H:%M:%S", time.localtime(secs))


def objectToBeautifiedText(obj):
	return json.dumps(serialize(obj), indent=4, ensure_ascii=False)


def objectToBash(obj, bashVars=None, level=0):
	"""
	Converts `obj` into bash-compatible format.

	:type bashVars: dict
	:type level: int
	:rtype: dict
	"""
	if bashVars is None:
		bashVars = {}

	if level == 0:
		obj = serialize(obj)
		varName = 'RESULT'
		compress = True
	else:
		varName = 'RESULT%d' % level
		compress = False

	try:
		obj = obj.serialize()
	except AttributeError:
		pass

	try:
		append = bashVars[varName].append
	except KeyError:
		emptyList = []
		bashVars[varName] = emptyList
		append = emptyList.append

	if isinstance(obj, (list, set)):
		append(u'(\n')
		for element in obj:
			if isinstance(element, (dict, list)):
				level += 1
				objectToBash(element, bashVars, level)
				append(u'RESULT%d=${RESULT%d[*]}' % (level, level))
			else:
				objectToBash(element, bashVars, level)
			append(u'\n')
		append(u')')
	elif isinstance(obj, dict):
		append(u'(\n')
		for (key, value) in obj.items():
			append('%s=' % key)
			if isinstance(value, (dict, list)):
				level += 1
				objectToBash(value, bashVars, level)
				append(u'${RESULT%d[*]}' % level)
			else:
				objectToBash(value, bashVars, level)
			append(u'\n')
		append(u')')
	elif obj is None:
		append(u'""')
	else:
		append(u'"%s"' % forceUnicode(obj))

	if compress:
		for key, value in bashVars.items():
			bashVars[key] = u''.join(value)

	return bashVars


def objectToHtml(obj, level=0):
	if level == 0:
		obj = serialize(obj)

	html = []
	append = html.append

	if isinstance(obj, (list, set)):
		append(u'[')
		if len(obj) > 0:
			append(u'<div style="padding-left: 3em;">')
			for i, currentElement in enumerate(obj):
				append(objectToHtml(currentElement, level + 1))
				if i < len(obj) - 1:
					append(u',<br />\n')
			append(u'</div>')
		append(u']')
	elif isinstance(obj, dict):
		append(u'{')
		if len(obj) > 0:
			append(u'<div style="padding-left: 3em;">')
			for i, (key, value) in enumerate(obj.items()):
				append(u'<font class="json_key">')
				append(objectToHtml(key))
				append(u'</font>: ')
				append(objectToHtml(value, level + 1))
				if i < len(obj) - 1:
					append(u',<br />\n')
			append(u'</div>')
		append(u'}')
	elif isinstance(obj, bool):
		append(str(obj).lower())
	elif obj is None:
		append('null')
	else:
		if isinstance(obj, str):
			append(replaceSpecialHTMLCharacters(obj).join((u'"', u'"')))
		else:
			append(replaceSpecialHTMLCharacters(obj))

	return u''.join(html)


def replaceSpecialHTMLCharacters(text):
	return forceUnicode(text)\
		.replace(u'\r', u'')\
		.replace(u'\t', u'   ')\
		.replace(u'&', u'&amp;')\
		.replace(u'"', u'&quot;')\
		.replace(u"'", u'&apos;')\
		.replace(u' ', u'&nbsp;')\
		.replace(u'<', u'&lt;')\
		.replace(u'>', u'&gt;')\
		.replace(u'\n', u'<br />\n')


def combineVersions(obj):
	"""
	Returns the combination of product and package version.

	:type obj: Product, ProductOnClient, ProductOnDepot
	:return: The version.
	:rtype: str
	"""
	return '{0.productVersion}-{0.packageVersion}'.format(obj)


def compareVersions(v1, condition, v2):
	"""
	Compare the versions `v1` and `v2` with the given `condition`.

	`condition` may be one of `==`, `<`, `<=`, `>`, `>=`.

	Versions will be made the same length by appending '.0' until they
	match.
	If `1.0.0` and `2` are compared the latter will be viewed as `2.0.0`.
	If a version contains a `~` that character and everything following
	it will not be taken into account.

	:raises ValueError: If invalid value for version or condition if given.
	:rtype: bool
	:return: If the comparison matches this will return True.
	"""
	def removePartAfterWave(versionString):
		if "~" in versionString:
			return versionString[:versionString.find("~")]
		else:
			return versionString

	def splitProductAndPackageVersion(versionString):
		productVersion = packageVersion = u'0'

		match = re.search(r'^\s*([\w.]+)-*([\w.]*)\s*$', versionString)
		if not match:
			raise ValueError(u"Bad version string '%s'" % versionString)

		productVersion = match.group(1)
		if match.group(2):
			packageVersion = match.group(2)

		return Version(productVersion, packageVersion)

	def makeEqualLength(first, second):
		while len(first) < len(second):
			first.append(u'0')

		while len(second) < len(first):
			second.append(u'0')

	def splitValue(value):
		match = re.search(r'^(\d+)(\D*.*)$', value)
		if match:
			return int(match.group(1)), match.group(2)
		else:
			match = re.search(r'^(\D+)(\d*.*)$', value)
			if match:
				return match.group(1), match.group(2)

		return u'', value

	if not condition:
		condition = u'=='
	if condition not in (u'==', u'=', u'<', u'<=', u'>', u'>='):
		raise ValueError(u"Bad condition '%s'" % condition)
	if condition == u'=':
		condition = u'=='

	v1 = removePartAfterWave(forceUnicode(v1))
	v2 = removePartAfterWave(forceUnicode(v2))

	version = splitProductAndPackageVersion(v1)
	otherVersion = splitProductAndPackageVersion(v2)
	logger.debug2("Versions: %s, %s", version, otherVersion)

	comparisons = (
		(version.product, otherVersion.product),
		(version.package, otherVersion.package)
	)

	for first, second in comparisons:
		logger.debug2("Comparing %s with %s...", first, second)
		firstParts = first.split(u'.')
		secondParts = second.split(u'.')
		makeEqualLength(firstParts, secondParts)

		for value, otherValue in zip(firstParts, secondParts):
			while value or otherValue:
				cv1, value = splitValue(value)
				cv2, otherValue = splitValue(otherValue)

				if cv1 == u'':
					cv1 = chr(1)
				if cv2 == u'':
					cv2 = chr(1)

				if cv1 == cv2:
					logger.debug2(u"%s == %s => continue", cv1, cv2)
					continue

				if not isinstance(cv1, int):
					cv1 = u"'%s'" % cv1
				if not isinstance(cv2, int):
					cv2 = u"'%s'" % cv2

				logger.debug2(u"Is %s %s %s?", cv1, condition, cv2)
				conditionFulfilled = eval(u"%s %s %s" % (cv1, condition, cv2))
				if not conditionFulfilled:
					logger.debug(u"Unfulfilled condition: %s %s %s", version, condition, otherVersion)
					return False

				logger.debug(u"Fulfilled condition: %s %s %s", version, condition, otherVersion)
				return True

	if u'=' not in condition:
		logger.debug(u"Unfulfilled condition: %s %s %s", version, condition, otherVersion)
		return False

	logger.debug(u"Fulfilled condition: %s %s %s", version, condition, otherVersion)
	return True


def removeUnit(x):
	'''
	Take a string representing a byte-based size and return the
	value in bytes.

	:param x: str
	:returns: `x` in bytes.
	:rtype: int or float
	'''
	x = forceUnicode(x)
	match = UNIT_REGEX.search(x)
	if not match:
		return x

	if u'.' in match.group(1):
		value = float(match.group(1))
	else:
		value = int(match.group(1))

	unit = match.group(2)
	mult = 1000

	if unit.lower().endswith('hz'):
		unit = unit[:-2]
	elif unit.lower().endswith('bits'):
		mult = 1024
		unit = unit[:-4]
	elif unit.lower().endswith('b'):
		mult = 1024
		unit = unit[:-1]
	elif unit.lower().endswith(('s', 'v')):
		unit = unit[:-1]

	if unit.endswith('n'):
		return float(value) / (mult * mult)
	elif unit.endswith('m'):
		return float(value) / mult
	elif unit.lower().endswith('k'):
		return value * mult
	elif unit.endswith('M'):
		return value * mult * mult
	elif unit.endswith('G'):
		return value * mult * mult * mult

	return value


def blowfishEncrypt(key, cleartext):
	"""
	Takes `cleartext` string, returns hex-encoded,
	blowfish-encrypted string.

	:type key: str
	:type cleartext: str
	:raises BlowfishError: In case things go wrong.
	:rtype: str
	"""
	if not key:
		raise BlowfishError("Missing key")

	key = _prepareBlowfishKey(key)
	cleartext = forceUnicode(cleartext)

	while len(cleartext) % 8 != 0:
		# Fill up with \0 until length is a mutiple of 8
		cleartext += chr(0)

	blowfish = Blowfish.new(key, Blowfish.MODE_CBC, BLOWFISH_IV)
	try:
		crypt = blowfish.encrypt(cleartext.encode("utf-8"))
	except Exception as encryptError:
		logger.logException(encryptError, LOG_DEBUG)
		raise BlowfishError(u"Failed to encrypt")

	return crypt.hex()


def blowfishDecrypt(key, crypt):
	"""
	Takes hex-encoded, blowfish-encrypted string,
	returns cleartext string.

	:type key: str
	:param crypt: The encrypted text as hex.
	:type crypt: str
	:raises BlowfishError: In case things go wrong.
	:rtype: str
	"""
	if not key:
		raise BlowfishError("Missing key")

	key = _prepareBlowfishKey(key)
	crypt = bytes.fromhex(crypt)

	blowfish = Blowfish.new(key, Blowfish.MODE_CBC, BLOWFISH_IV)
	try:
		cleartext = blowfish.decrypt(crypt)
	except Exception as decryptError:
		logger.debug(decryptError, exc_info=True)
		raise BlowfishError("Failed to decrypt")

	# Remove possible \0-chars
	cleartext = cleartext.rstrip(b'\0')

	try:
		return cleartext.decode("utf-8")
	except Exception as e:
		logger.error(e)
		raise BlowfishError(u"Failed to convert decrypted text to unicode.")


def _prepareBlowfishKey(key: str) -> bytes:
	"Transform the key into hex."
	try:
		key = forceUnicode(key).encode()
		return codecs.decode(key, "hex")
	except (binascii.Error, Exception) as err:
		raise BlowfishError(f"Unable to prepare key: {err}")


def encryptWithPublicKeyFromX509CertificatePEMFile(data, filename):
	"""
	Encrypt the data by using the certificate.

	:type data: str
	:type filename: str
	:param filename: The path to the certificate to use.
	:rtype: bytes
	"""
	import M2Crypto

	cert = M2Crypto.X509.load_cert(filename)
	rsa = cert.get_pubkey().get_rsa()
	padding = M2Crypto.RSA.pkcs1_oaep_padding

	def encrypt():
		for parts in chunk(data, size=32):
			partedText = ''.join(parts)
			yield rsa.public_encrypt(data=partedText.encode(), padding=padding)

	return b''.join(encrypt())


def decryptWithPrivateKeyFromPEMFile(data, filename):
	"""
	Decrypt the data by using the certificate.

	:type data: bytes
	:type filename: str
	:param filename: The path to the certificate to use.
	:rtype: str
	"""
	import M2Crypto

	privateKey = M2Crypto.RSA.load_key(filename)
	padding = M2Crypto.RSA.pkcs1_oaep_padding

	def decrypt():
		for parts in chunk(data, size=256):
			newBytes = bytearray(parts)
			decr = privateKey.private_decrypt(data=bytes(newBytes), padding=padding)
			yield decr

	return (b''.join(decrypt())).decode()


def findFilesGenerator(directory, prefix=u'', excludeDir=None, excludeFile=None, includeDir=None, includeFile=None, returnDirs=True, returnLinks=True, followLinks=False, repository=None):
	directory = forceFilename(directory)
	prefix = forceUnicode(prefix)

	if excludeDir:
		if not isRegularExpressionPattern(excludeDir):
			excludeDir = re.compile(forceUnicode(excludeDir))
	else:
		excludeDir = None

	if excludeFile:
		if not isRegularExpressionPattern(excludeFile):
			excludeFile = re.compile(forceUnicode(excludeFile))
	else:
		excludeFile = None

	if includeDir:
		if not isRegularExpressionPattern(includeDir):
			includeDir = re.compile(forceUnicode(includeDir))
	else:
		includeDir = None

	if includeFile:
		if not isRegularExpressionPattern(includeFile):
			includeFile = re.compile(forceUnicode(includeFile))
	else:
		includeFile = None

	returnDirs = forceBool(returnDirs)
	returnLinks = forceBool(returnLinks)
	followLinks = forceBool(followLinks)

	if repository:
		islink = repository.islink
		isdir = repository.isdir
		listdir = repository.listdir
	else:
		islink = os.path.islink
		isdir = os.path.isdir
		listdir = os.listdir

	for entry in listdir(directory):
		pp = os.path.join(prefix, entry)
		dp = os.path.join(directory, entry)
		isLink = False
		if islink(dp):
			isLink = True
			if not returnLinks and not followLinks:
				continue
		if isdir(dp) and (not isLink or followLinks):
			if excludeDir and re.search(excludeDir, entry):
				logger.debug(u"Excluding dir '%s' and containing files", entry)
				continue
			if includeDir:
				if not re.search(includeDir, entry):
					continue
				logger.debug(u"Including dir '%s' and containing files", entry)
			if returnDirs:
				yield pp
			yield from findFilesGenerator(
				directory=dp,
				prefix=pp,
				excludeDir=excludeDir,
				excludeFile=excludeFile,
				includeDir=includeDir,
				includeFile=includeFile,
				returnDirs=returnDirs,
				returnLinks=returnLinks,
				followLinks=followLinks,
				repository=repository
			)
			continue

		if excludeFile and re.search(excludeFile, entry):
			if isLink:
				logger.debug(u"Excluding link '%s'", entry)
			else:
				logger.debug(u"Excluding file '%s'", entry)
			continue

		if includeFile:
			if not re.search(includeFile, entry):
				continue
			if isLink:
				logger.debug(u"Including link '%s'", entry)
			else:
				logger.debug(u"Including file '%s'", entry)
		yield pp

def findFiles(directory, prefix=u'', excludeDir=None, excludeFile=None, includeDir=None, includeFile=None, returnDirs=True, returnLinks=True, followLinks=False, repository=None):
	return list(findFilesGenerator(directory, prefix, excludeDir, excludeFile, includeDir, includeFile, returnDirs, returnLinks, followLinks, repository))

if sys.version_info >= (3, 7):
	def isRegularExpressionPattern(object):
		return isinstance(object, re.Pattern)
else:
	def isRegularExpressionPattern(object):
		return "SRE_Pattern" in str(type(object))


def ipAddressInNetwork(ipAddress, networkAddress):
	"""
	Checks if the given IP address is in the given network range.
	Returns ``True`` if the given address is part of the network.
	Returns ``False`` if the given address is not part of the network.

	:param ipAddress: The IP which we check.
	:type ipAddress: str
	:param networkAddress: The network address written with slash notation.
	:type networkAddress: str
	"""
	if (
		not isinstance(ipAddress, ipaddress.IPv4Address) and
		not isinstance(ipAddress, ipaddress.IPv6Address)
	):
		ipAddress = ipaddress.ip_address(ipAddress)
	if isinstance(ipAddress, ipaddress.IPv6Address) and ipAddress.ipv4_mapped:
		ipAddress = ipAddress.ipv4_mapped
	
	if (
		not isinstance(networkAddress, ipaddress.IPv4Network) and
		not isinstance(networkAddress, ipaddress.IPv6Network)
	):
		networkAddress = ipaddress.ip_network(networkAddress)
	
	return ipAddress in networkAddress


def getfqdn(name='', conf=None):
	"""
	Get the fqdn.

	If ``name`` is not given it will try various ways to get a valid
	fqdn from the current host.
	If ``conf`` but no name is given it will try to read the FQDN from
	the specified configuration file.
	"""
	if not name:
		try:
			return forceFqdn(os.environ["OPSI_HOSTNAME"])
		except KeyError:
			# not set in environment.
			pass

		# lazy import to avoid circular dependency
		from OPSI.Util.Config import getGlobalConfig

		if conf is not None:
			hostname = getGlobalConfig('hostname', conf)
		else:
			hostname = getGlobalConfig('hostname')

		if hostname:
			return forceFqdn(hostname)

	return forceFqdn(socket.getfqdn(name))


def removeDirectory(directory):
	"""
	Removing an directory.

	If this fails with shutil it will try to use system calls.

	.. versionadded:: 4.0.5.1


	:param directory: Path to the directory
	:tye directory: str
	"""
	logger.debug('Removing directory: %s', directory)
	try:
		shutil.rmtree(directory)
	except UnicodeDecodeError:
		# See http://bugs.python.org/issue3616
		logger.info(
			u'Client data directory seems to contain filenames '
			u'with unicode characters. Trying fallback.'
		)

		import OPSI.System  # late import to avoid circular dependency
		OPSI.System.execute('rm -rf {dir}'.format(dir=directory))


def chunk(iterable, size):
	"""
	Returns chunks (parts) of a specified `size` from `iterable`.
	It will not pad (fill) the chunks.

	This works lazy and therefore can be used with any iterable without
	much overhead.

	Original recipe from http://stackoverflow.com/a/22045226
	"""
	it = iter(iterable)
	return iter(lambda: tuple(islice(it, size)), ())


@lru_cache(maxsize=4)
def getPublicKey(data):
	# Key type can be found in 4:11.
	rest = data[11:]
	count = 0
	mp = []
	for _ in range(2):
		length = struct.unpack('>L', rest[count:count + 4])[0]
		mp.append(bytes_to_long(rest[count + 4:count + 4 + length]))
		count += 4 + length

	return RSA.construct((mp[1], mp[0]))


def merge(thing1 : Any, thing2 : Any) -> Any:
	"""
	Merges two things.

	This method expects two objects and attempts to merge them into one.
	To do this, depending on the types, these rules are applied:

	- If they are the same, only one of them is returned.
	- If any one of them is None, the other one is returned.
	- If their type is different, None is returned.
	- If they are both lists, a list containing all entries is returned.
	- If they are both dicts, a new dict is returned containing all
		keys involved with recursively merged values.
	- If none of these conditions hold (e.g. thing1 = 2 and thing2 = 4)
		None is returned (as for different types).

	:param thing1: First thing to merge
	:type Any:
	:param thing2: Second thing to merge
	:type Any:
	:returns: Result of the merging.
	:rtype: Any
	"""
	if thing1 == thing2:
		return thing1
	if thing1 is None:
		return thing2
	if thing2 is None:
		return thing1

	if isinstance(thing1, list) and isinstance(thing2, list):
		result = thing1.copy()
		for x in thing2:
			if x not in result:
				result.append(x)
		return result
	if isinstance(thing1, dict) and isinstance(thing2, dict):
		result = {}
		allkeys = set(thing1.keys()).union(set(thing2.keys()))
		for key in allkeys:
			result.update({key : merge(thing1.get(key), thing2.get(key))})
		return result
	if isinstance(thing1, set) and isinstance(thing2, set):
		result = set([])
		result = result.union(thing1)
		result = result.union(thing2)
		return result
	
	if str(thing1) == str(thing2):		# allow for things like "1.0" and 1.0 to be merged
		return str(thing1)

	return None
