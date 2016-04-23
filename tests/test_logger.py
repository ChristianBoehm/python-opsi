#! /usr/bin/env python
# -*- coding: utf-8 -*-

# This file is part of python-opsi.
# Copyright (C) 2015-2016 uib GmbH <info@uib.de>

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
Testing our logger.

:author: Niko Wenselowski <n.wenselowski@uib.de>
:license: GNU Affero General Public License version 3
"""

from __future__ import absolute_import

import os
import sys
import warnings
from io import BytesIO as StringIO

import OPSI.Logger
import pytest

from .helpers import cd, mock, unittest, workInTemporaryDirectory

# Log level that will result in log output.
LOGGING_LEVELS = [
    OPSI.Logger.LOG_CONFIDENTIAL,
	OPSI.Logger.LOG_DEBUG2,
	OPSI.Logger.LOG_DEBUG,
	OPSI.Logger.LOG_INFO,
	OPSI.Logger.LOG_NOTICE,
	OPSI.Logger.LOG_WARNING,
	OPSI.Logger.LOG_ERROR,
	OPSI.Logger.LOG_CRITICAL,
	OPSI.Logger.LOG_ESSENTIAL,
	OPSI.Logger.LOG_COMMENT
]

@pytest.yield_fixture
def logger():
	logger = OPSI.Logger.LoggerImplementation()

	try:
		yield logger
	finally:
		logger.setConsoleLevel(OPSI.Logger.LOG_NONE)
		logger.setFileLevel(OPSI.Logger.LOG_NONE)


def testLoggingMessage(logger):
	level = OPSI.Logger.LOG_CONFIDENTIAL
	logger.setConsoleLevel(level)

	messageBuffer = StringIO()
	with mock.patch('OPSI.Logger.sys.stdin', messageBuffer):
		with mock.patch('OPSI.Logger.sys.stderr', messageBuffer):
			logger.log(level, "This is not a test!", raiseException=True)

	assert "This is not a test!" in messageBuffer.getvalue()


@pytest.mark.parametrize("logLevel", [OPSI.Logger.LOG_NONE] + LOGGING_LEVELS)
def testChangingConsoleLogLevel(logger, logLevel):
	logger.setConsoleLevel(logLevel)
	assert logLevel == logger.getConsoleLevel()


@pytest.mark.parametrize("logLevel", LOGGING_LEVELS)
def testLoggingUnicode(logger, logLevel):
	logger.setConsoleLevel(logLevel)

	messageBuffer = StringIO()
	with mock.patch('OPSI.Logger.sys.stdin', messageBuffer):
		with mock.patch('OPSI.Logger.sys.stderr', messageBuffer):
			logger.log(logLevel, u"Heävy Metäl Ümläüts! Öy!", raiseException=True)

	# Currently this has to be suffice
	# TODO: better check for logged string.
	assert messageBuffer.getvalue()


def test_logTwisted(logger):
	log = pytest.importorskip("twisted.python.log")

	logger.setConsoleLevel(OPSI.Logger.LOG_DEBUG)
	logger.setLogFormat('[%l] %M')

	err = StringIO()

	with mock.patch('OPSI.Logger.sys.stdin', err):
		with mock.patch('OPSI.Logger.sys.stderr', err):
			logger.startTwistedLogging()

			value = err.getvalue()
			assert "" != value
			assert value == "[{0:d}] [twisted] Log opened.\n".format(OPSI.Logger.LOG_DEBUG)
			err.seek(0)
			err.truncate(0)

			log.msg("message")
			value = err.getvalue()
			assert "" != value
			assert value == "[{0:d}] [twisted] message\n".format(OPSI.Logger.LOG_DEBUG)
			err.seek(0)
			err.truncate(0)

			log.err("message")
			value = err.getvalue()
			assert value == "[{0:d}] [twisted] 'message'\n".format(OPSI.Logger.LOG_ERROR)


def testPatchingShowwarnings(logger):
	originalWarningFunction = warnings.showwarning
	assert originalWarningFunction is warnings.showwarning

	try:
		logger.logWarnings()
		assert originalWarningFunction is not warnings.showwarning
	finally:
		# Making sure that the switched function is
		# resetted to it's default.
		warnings.showwarning = originalWarningFunction


def testLoggingFromWarningsModule(logger):
	logger.setConsoleLevel(OPSI.Logger.LOG_WARNING)
	logger.setLogFormat('[%l] %M')

	messageBuffer = StringIO()

	with mock.patch('OPSI.Logger.sys.stdin', messageBuffer):
		with mock.patch('OPSI.Logger.sys.stderr', messageBuffer):
			try:
				logger.logWarnings()

				warnings.warn("usermessage")
				warnings.warn("another message", DeprecationWarning)
				warnings.warn("message", DeprecationWarning, stacklevel=2)
			finally:
				# Making sure that the switched function is
				# resetted to it's default.
				warnings.showwarning = OPSI.Logger._showwarning

	value = messageBuffer.getvalue()

	assert value.startswith("[{0:d}]".format(OPSI.Logger.LOG_WARNING))
	assert "UserWarning: usermessage" in value

	if sys.version_info < (2, 7):
		# Changed in version 2.7: DeprecationWarning is ignored by default.
		# Source: https://docs.python.org/2.7/library/warnings.html#warning-categories
		assert "DeprecationWarning: message" in value
		assert "DeprecationWarning: another message" in value


@pytest.mark.parametrize("message, logLevel", [
	("my password", OPSI.Logger.LOG_CONFIDENTIAL),
	("beepbeepbeepbeeeeeeeeeep", OPSI.Logger.LOG_DEBUG2),
	("Beep, beep.", OPSI.Logger.LOG_DEBUG),
	("The Stark Tower", OPSI.Logger.LOG_INFO),
	("Hulk not angry", OPSI.Logger.LOG_NOTICE),
	("Loki lifes!", OPSI.Logger.LOG_WARNING),
	("under 9000", OPSI.Logger.LOG_ERROR),
	("over 9000", OPSI.Logger.LOG_CRITICAL),
	("never miss", OPSI.Logger.LOG_ESSENTIAL),
	("my words blabla", OPSI.Logger.LOG_COMMENT),
])
def testLogLevelIsShownInOutput(logger, message, logLevel):
	logger.setConsoleLevel(logLevel)
	logger.setLogFormat('[%l] %M')

	messageBuffer = StringIO()

	with mock.patch('OPSI.Logger.sys.stdin', messageBuffer):
		with mock.patch('OPSI.Logger.sys.stderr', messageBuffer):
			logger.log(logLevel, message)
			value = messageBuffer.getvalue()
			assert value.startswith("[{0:d}]".format(logLevel))
			assert message in value
			assert value.endswith('message')


def testConfidentialStringsAreNotLogged(logger):
	secretWord = 'mySecr3tP4ssw0rd!'

	logger.addConfidentialString(secretWord)
	logger.setConsoleLevel(OPSI.Logger.LOG_DEBUG2)

	messageBuffer = StringIO()
	with mock.patch('OPSI.Logger.sys.stdin', messageBuffer):
		with mock.patch('OPSI.Logger.sys.stderr', messageBuffer):
			logger.notice("Psst... {0}".format(secretWord))

	value = messageBuffer.getvalue()
	assert secretWord not in value
	assert "Psst... " in value
	assert "*** confidential ***" in value


def testConfidentialStringsCanNotBeEmpty(logger):
	with pytest.raises(ValueError):
		logger.addConfidentialString('')


def testLogFormatting(logger):
	logger.setConsoleLevel(OPSI.Logger.LOG_CONFIDENTIAL)
	logger.setLogFormat('[%l - %L] %F %M')

	messageBuffer = StringIO()
	with mock.patch('OPSI.Logger.sys.stdin', messageBuffer):
		with mock.patch('OPSI.Logger.sys.stderr', messageBuffer):
			logger.debug("Chocolate Starfish")

	value = messageBuffer.getvalue()
	assert '[7 - debug] test_logger.py Chocolate Starfish', value.strip()


def testSettingConfidentialStrings(logger):
	confidential = ["Momente", "Wahnsinn"]
	logger.setConfidentialStrings(confidential)

	logger.setConsoleLevel(OPSI.Logger.LOG_DEBUG2)

	messageBuffer = StringIO()
	with mock.patch('OPSI.Logger.sys.stdin', messageBuffer):
		with mock.patch('OPSI.Logger.sys.stderr', messageBuffer):
			logger.notice("Die Momente, die es wert sind, ziehen so schnell vorbei")
			logger.notice("So schnell, so weit")
			logger.notice("Der Wahnsinn folgt jetzt nicht mehr dem Asphalt")
			logger.notice("Du lässt ihn zurück")

	value = messageBuffer.getvalue()
	for word in confidential:
		assert word not in value
	assert "So schnell, so weit" in value


def testChangingDirectoriesDoesNotChangePathOfLog(logger):
	with workInTemporaryDirectory():
		logger.setLogFile('test.log')
		logger.setFileLevel(OPSI.Logger.LOG_DEBUG)
		logger.warning('abc')

		assert os.path.exists('test.log')

		os.mkdir('subdir')
		with cd('subdir'):
			assert not os.path.exists('test.log')
			logger.warning('def')
			assert not os.path.exists('test.log')


def testSettingLogPathToNone(logger):
	logger.setLogFile(None)
