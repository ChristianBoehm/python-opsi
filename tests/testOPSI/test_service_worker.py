# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Testing the workers.
"""

import gzip
import zlib

try:
	from cStringIO import StringIO
except ImportError:
	from io import StringIO

import pytest

from OPSI.Service.Worker import WorkerOpsi, WorkerOpsiJsonRpc
from OPSI.Util.HTTP import gzipEncode, deflateEncode


class FakeHeader(object):
	def __init__(self, headers=None):
		self.headers = headers or {}

	def hasHeader(self, header):
		return header in self.headers

	def getHeader(self, header):
		return self.headers[header]


class FakeDictHeader(FakeHeader):
	def getHeader(self, header):
		class ReturnWithMediaType:
			def __init__(self, key):
				self.mediaType = key

		return dict((ReturnWithMediaType(self.headers[key]), self.headers[key]) for key in self.headers if key.startswith(header))


class FakeMediaType(object):
	def __init__(self, type):
		self.mediaType = type

	def __str__(self):
		return self.mediaType

	def __repr__(self):
		return "FakeMediaType({})".format(self.type)


class FakeRequest(object):
	def __init__(self, headers=None):
		self.headers = headers or FakeHeader()
		self.method = 'POST'


class FakeRPC(object):
	def __init__(self, result=None):
		self.result = result or None

	def getResponse(self):
		return self.result


@pytest.mark.obsolete
def testReturningEmptyResponse():
	"""
	Making sure that an empty uncompressed response is returned.

	We check the headers of the request and also make sure that
	the content is "null".
	"""
	worker = WorkerOpsiJsonRpc(service=None, request=FakeRequest(), resource=None)

	result = worker._generateResponse(None)
	assert 200 == result.code
	assert result.headers.hasHeader('content-type')
	assert ['application/json;charset=utf-8'] == result.headers.getRawHeaders('content-type')
	assert not result.headers.hasHeader('content-encoding')
	assert 'null' == str(result.stream.read())


@pytest.mark.obsolete
def testHandlingMultipleRPCs():
	"""
	With multiple RPCs the results are returned in a list.

	We do not use any compression in this testcase.
	"""
	worker = WorkerOpsiJsonRpc(service=None, request=FakeRequest(), resource=None)
	worker._rpcs = [
		FakeRPC(), FakeRPC(1), FakeRPC(u"FÄKE!"),
		FakeRPC({"Narziss": "Morgen Nicht Geboren"})
	]

	result = worker._generateResponse(None)
	assert 200 == result.code
	assert result.headers.hasHeader('content-type')
	assert ['application/json;charset=utf-8'] == result.headers.getRawHeaders('content-type')
	assert not result.headers.hasHeader('content-encoding')
	assert '[null, 1, "F\xc3\x84KE!", {"Narziss": "Morgen Nicht Geboren"}]' == str(result.stream.read())


@pytest.mark.obsolete
def testHandlingSingleResult():
	"""
	A single RPC result must not be returned in a list.
	"""
	worker = WorkerOpsiJsonRpc(service=None, request=FakeRequest(), resource=None)
	worker._rpcs = [FakeRPC("Hallo Welt")]

	result = worker._generateResponse(None)
	assert 200 == result.code
	assert result.headers.hasHeader('content-type')
	assert ['application/json;charset=utf-8'] == result.headers.getRawHeaders('content-type')
	assert not result.headers.hasHeader('content-encoding')
	assert '"Hallo Welt"' == str(result.stream.read())


@pytest.mark.obsolete
def testHandlingSingleResultConsistingOfList():
	"""
	If a single result is made the result is a list this list must not be unpacked.
	"""
	worker = WorkerOpsiJsonRpc(service=None, request=FakeRequest(), resource=None)
	worker._rpcs = [FakeRPC(["Eins", "Zwei", "Drei"])]

	result = worker._generateResponse(None)
	assert 200 == result.code
	assert result.headers.hasHeader('content-type')
	assert ['application/json;charset=utf-8'] == result.headers.getRawHeaders('content-type')
	assert not result.headers.hasHeader('content-encoding')
	assert '["Eins", "Zwei", "Drei"]' == str(result.stream.read())


@pytest.mark.obsolete
def testCompressingResponseDataWithGzip():
	"""
	Responding with data compressed by gzip.
	"""
	testHeader = FakeHeader({"Accept-Encoding": "gzip"})
	request = FakeRequest(testHeader)
	worker = WorkerOpsiJsonRpc(service=None, request=request, resource=None)

	result = worker._generateResponse(None)
	assert 200 == result.code
	assert result.headers.hasHeader('content-type')
	assert ['application/json;charset=utf-8'] == result.headers.getRawHeaders('content-type')
	assert ['gzip'] == result.headers.getRawHeaders('content-encoding')

	sdata = result.stream.read()

	with gzip.GzipFile(fileobj=StringIO(sdata), mode="r") as gzipfile:
		data = gzipfile.read()

	assert 'null' == data


@pytest.mark.obsolete
def testCompressingResponseDataWithDeflate():
	"""
	Responding with data compressed by deflate.
	"""
	testHeader = FakeHeader({"Accept-Encoding": "deflate"})
	request = FakeRequest(testHeader)
	worker = WorkerOpsiJsonRpc(service=None, request=request, resource=None)

	result = worker._generateResponse(None)
	assert 200 == result.code
	assert result.headers.hasHeader('content-type')
	assert ['application/json;charset=utf-8'] == result.headers.getRawHeaders('content-type')
	assert ['deflate'] == result.headers.getRawHeaders('content-encoding')

	sdata = result.stream.read()
	data = zlib.decompress(sdata)
	assert 'null' == data


@pytest.mark.obsolete
def testCompressingResponseIfInvalidMimetype():
	"""
	Staying backwards compatible.

	Old clients connect to the server and send an "Accept" with
	the invalid mimetype "gzip-application/json-rpc".
	We must respond to these clients because not doing so could
	result in rendering an opsi landscape unresponding.

	The returned "content-type" is invalid and makes no sense.
	Correct would be "application/json".
	The returned content-encoding is "gzip" but the content
	is acutally compressed with deflate.
	"""
	testHeader = FakeDictHeader({
		"Accept": "gzip-application/json-rpc",
		"invalid": "ignoreme"
	})
	request = FakeRequest(testHeader)
	worker = WorkerOpsiJsonRpc(service=None, request=request, resource=None)

	result = worker._generateResponse(None)
	assert 200 == result.code
	assert result.headers.hasHeader('content-type')
	assert ['gzip'] == result.headers.getRawHeaders('content-encoding')
	assert ['gzip-application/json;charset=utf-8'] == result.headers.getRawHeaders('content-type')

	sdata = result.stream.read()
	data = zlib.decompress(sdata)
	assert 'null' == data


@pytest.mark.obsolete
def testReturningPlainCalls():
	testHeader = FakeDictHeader({"Accept": "text/plain"})
	request = FakeRequest(testHeader)
	worker = WorkerOpsiJsonRpc(service=None, request=request, resource=None)

	result = worker._generateResponse(None)
	assert 200 == result.code
	assert result.headers.hasHeader('content-type')
	assert ['application/json;charset=utf-8'] == result.headers.getRawHeaders('content-type')
	assert not result.headers.hasHeader('content-encoding')

	data = result.stream.read()
	assert 'null' == str(data)


@pytest.mark.obsolete
def testDecodingOldCallQuery():
	"Simulating opsi 4.0.6 with invalid MIME type handling."
	r = FakeRequest(headers=FakeHeader(
		{
			"content-encoding": ["gzip"],
			"content-type": FakeMediaType("gzip-application/json-rpc"),
		}
	))

	worker = WorkerOpsi(service=None, request=r, resource=None)
	worker.query = zlib.compress("Test 1234")
	worker._decodeQuery(None)
	assert u'Test 1234' == worker.query


@pytest.mark.parametrize("contentEncoding, compressor", [
	["gzip", gzipEncode],
	["deflate", deflateEncode],
	[None, lambda x: x],
])
@pytest.mark.obsolete
def testDecodingCallQuery(contentEncoding, compressor):
	headers = {
		"content-type": FakeMediaType("application/json"),
	}

	if contentEncoding:
		headers['content-encoding'] = [contentEncoding]

	r = FakeRequest(headers=FakeHeader(headers))

	worker = WorkerOpsi(service=None, request=r, resource=None)
	worker.query = compressor("Test 1234")
	worker._decodeQuery(None)
	assert u'Test 1234' == worker.query
