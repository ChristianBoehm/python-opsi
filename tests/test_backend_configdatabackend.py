#! /usr/bin/env python
# -*- coding: utf-8 -*-

# This file is part of python-opsi.
# Copyright (C) 2015 uib GmbH <info@uib.de>

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
Testing ConfigDataBackend.

:author: Niko Wenselowski <n.wenselowski@uib.de>
:license: GNU Affero General Public License version 3
"""

from __future__ import absolute_import

import codecs
import gzip
import os
import shutil
import tempfile
from contextlib import closing  # Needed for Python 2.6

import OPSI.Backend.Backend
from OPSI.Types import BackendBadValueError

from .helpers import mock, unittest


class ConfigDataBackendTestCase(unittest.TestCase):
	def setUp(self):
		self.logDirectory = tempfile.mkdtemp()
		self.logDirectoryPatch = mock.patch('OPSI.Backend.Backend.LOG_DIR', self.logDirectory)
		self.logDirectoryPatch.start()

	def tearDown(self):
		if os.path.exists(self.logDirectory):
			shutil.rmtree(self.logDirectory)

		self.logDirectoryPatch.stop()

	def testReadingLogFailsIfTypeUnknown(self):
		cdb = OPSI.Backend.Backend.ConfigDataBackend()

		self.assertRaises(BackendBadValueError, cdb.log_read, 'blablabla')

	def testReadingLogRequiresObjectId(self):
		cdb = OPSI.Backend.Backend.ConfigDataBackend()

		for logType in ('bootimage', 'clientconnect', 'userlogin', 'instlog'):
			print("Logtype: {0}".format(logType))
			self.assertRaises(BackendBadValueError, cdb.log_read, logType)

	def testReadingOpsiconfdLogDoesNotRequireObjectId(self):
		cdb = OPSI.Backend.Backend.ConfigDataBackend()
		cdb.log_read('opsiconfd')

	def testReadingNonExistingLogReturnsEmptyString(self):
		"""
		Valid calls to read logs should return empty strings if no file
		does exist.
		"""
		cdb = OPSI.Backend.Backend.ConfigDataBackend()
		self.assertEquals("", cdb.log_read('opsiconfd'))
		self.assertEquals("", cdb.log_read('opsiconfd', 'unknown_object'))

	def testOnlyValidLogTypesAreWritten(self):
		cdb = OPSI.Backend.Backend.ConfigDataBackend()
		self.assertRaises(BackendBadValueError, cdb.log_write, 'foobar', '')

	def testWritingLogRequiresObjectId(self):
		cdb = OPSI.Backend.Backend.ConfigDataBackend()
		self.assertRaises(BackendBadValueError, cdb.log_write, 'opsiconfd', None)

	def testWritingLogCreatesFile(self):
		cdb = OPSI.Backend.Backend.ConfigDataBackend()
		cdb.log_write('opsiconfd', 'data', objectId='foo.bar.baz')

		expectedLogPath = os.path.join(self.logDirectory, 'opsiconfd', 'foo.bar.baz.log')
		self.assertTrue(os.path.exists(expectedLogPath),
						"Log path {0} should exist.".format(expectedLogPath))

	def testWritingAndThenReadingDataFromLog(self):
		cdb = OPSI.Backend.Backend.ConfigDataBackend()
		cdb.log_write('opsiconfd', 'data', objectId='foo.bar.baz')

		self.assertEquals('data', cdb.log_read('opsiconfd', 'foo.bar.baz'))

	def testWritingAndThenReadingDataFromLogWithLimitedWrite(self):
		cdb = OPSI.Backend.Backend.ConfigDataBackend(maxLogSize=10)

		longData = 'data1\ndata2\ndata3\ndata4\n'
		cdb.log_write('opsiconfd', longData, objectId='foo.bar.baz')

		self.assertEquals('data4\n', cdb.log_read('opsiconfd', 'foo.bar.baz'))

	def testWritingAndThenReadingDataFromLogWithLimitedRead(self):
		cdb = OPSI.Backend.Backend.ConfigDataBackend()

		longData = 'data1\ndata2\ndata3\ndata4\n'
		cdb.log_write('opsiconfd', longData, objectId='foo.bar.baz')

		self.assertEquals('data4\n', cdb.log_read('opsiconfd', 'foo.bar.baz', maxSize=10))

	def testAppendingLog(self):
		cdb = OPSI.Backend.Backend.ConfigDataBackend(maxLogSize=10)

		longData = 'data1\ndata2\ndata3\ndata4\n'
		cdb.log_write('opsiconfd', longData, objectId='foo.bar.baz', append=True)
		cdb.log_write('opsiconfd', "data5\n", objectId='foo.bar.baz', append=True)

		self.assertEquals('data5\n', cdb.log_read('opsiconfd', 'foo.bar.baz'))

	def testWritingAndReadingLogWithoutLimits(self):
		# Not even the sky is the limit!
		cdb = OPSI.Backend.Backend.ConfigDataBackend(maxLogSize=0)

		longData = 'data1\ndata2\ndata3\ndata4\n'
		cdb.log_write('opsiconfd', longData, objectId='foo.bar.baz')

		self.assertEquals(longData, cdb.log_read('opsiconfd', 'foo.bar.baz', maxSize=0))

	def testAppendingRotatedLogs(self):
		cdb = OPSI.Backend.Backend.ConfigDataBackend()

		clientName = 'foo.bar.baz'
		logDir = os.path.join(self.logDirectory, "opsiconfd")
		os.mkdir(logDir)
		logPath = os.path.join(logDir, "{0}.log".format(clientName))
		with codecs.open(logPath, "w", 'utf-8') as f:
			f.write(u"Wo dann?\n")

		with codecs.open("{0}.1".format(logPath), "w", 'utf-8') as f:
			f.write(u"Hier nicht!\n")

		with codecs.open("{0}.2".format(logPath), "w", 'utf-8') as f:
			f.write(u"Wo ist der Mülleimer?\n")

		expectedResult = u"""Wo ist der Mülleimer?
Hier nicht!
Wo dann?
"""

		self.assertEquals(expectedResult, cdb.log_read('opsiconfd', clientName))
		self.assertEquals(expectedResult, cdb.log_read('opsiconfd', clientName, maxSize=False))

	def testAppendingGzippedRotatedLogs(self):
		cdb = OPSI.Backend.Backend.ConfigDataBackend()

		clientName = 'foo.bar.baz'
		logDir = os.path.join(self.logDirectory, "opsiconfd")
		os.mkdir(logDir)
		logPath = os.path.join(logDir, "{0}.log".format(clientName))
		with codecs.open(logPath, "w", 'utf-8') as f:
			f.write(u"Wo dann?\n")

		with open("{0}.1.gz".format(logPath), "wb") as f:
			with closing(gzip.GzipFile(fileobj=f, mode="w")) as gzipfile:
				gzipfile.write(u"Hier nicht!\n".encode('utf-8'))

		with open("{0}.2.gz".format(logPath), "wb") as f:
			with closing(gzip.GzipFile(fileobj=f, mode="w")) as gzipfile:
				gzipfile.write(u"Wo ist der Mülleimer?\n".encode('utf-8'))

		expectedResult = u"""Wo ist der Mülleimer?
Hier nicht!
Wo dann?
"""

		self.assertEquals(expectedResult, cdb.log_read('opsiconfd', clientName))
		self.assertEquals(expectedResult, cdb.log_read('opsiconfd', clientName, maxSize=False))


if __name__ == '__main__':
	unittest.main()
