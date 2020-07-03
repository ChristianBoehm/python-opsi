# -*- coding: utf-8 -*-
"""
:copyright: uib GmbH <info@uib.de>
This file is part of opsi - https://www.opsi.org

:license: GNU Affero General Public License version 3
"""

import io
import pytest
import logging
import requests

from contextlib import contextmanager

import opsicommon.logging
from opsicommon.logging import logger

MY_FORMAT = "%(log_color)s[%(opsilevel)d] [%(asctime)s.%(msecs)03d]%(reset)s [%(context)s] %(message)s"
OTHER_FORMAT = "[%(opsilevel)d] [%(asctime)s.%(msecs)03d] [%(context)s] %(message)s   (%(filename)s:%(lineno)d)"

@contextmanager
@pytest.fixture
def log_stream():
	stream = io.StringIO()
	handler = logging.StreamHandler(stream)
	try:
		logging.root.addHandler(handler)
		yield stream
	finally:
		logging.root.removeHandler(handler)

def test_simple_colored(log_stream):
	with log_stream as stream:
		opsicommon.logging.set_format(MY_FORMAT)
		opsicommon.logging.set_context({'firstcontext' : 'asdf', 'secondcontext' : 'jkl'})
		print(logger.filters)
		logger.error("test message")
		stream.seek(0)
		log = stream.read()
		assert "asdf" in log and "jkl" in log

def test_simple_plain(log_stream):
	with log_stream as stream:
		opsicommon.logging.set_format(OTHER_FORMAT)
		opsicommon.logging.set_context({'firstcontext' : 'asdf', 'secondcontext' : 'jkl'})
		logger.error("test message")
		stream.seek(0)
		log = stream.read()
		assert "asdf" in log and "jkl" in log

def test_contexts(log_stream):
	with log_stream as stream:
		opsicommon.logging.set_format(MY_FORMAT)
		opsicommon.logging.set_context({'firstcontext' : 'asdf', 'secondcontext' : 'jkl'})
		logger.error("test message")
		stream.seek(0)
		log = stream.read()
		assert "asdf" in log and "jkl" in log
		stream.seek(0)
		stream.truncate()

		opsicommon.logging.set_context({'firstcontext' : 'asdf'})
		logger.error("test message")
		stream.seek(0)
		log = stream.read()
		assert "asdf" in log and "jkl" not in log

		stream.seek(0)
		stream.truncate()
		opsicommon.logging.set_context({})
		logger.error("test message")
		stream.seek(0)
		log = stream.read()
		assert "asdf" not in log

		stream.seek(0)
		stream.truncate()
		opsicommon.logging.set_context("suddenly a string")
		logger.error("test message")
		stream.seek(0)
		log = stream.read()
		assert "suddenly a string" not in log	# must be given as dictionary

def test_foreign_logs(log_stream):
	with log_stream as stream:
		opsicommon.logging.set_format("%(message)s")
		logger.error("message before request")

		requests.get("http://www.uib.de")

		logger.error("message after request")
		stream.seek(0)
		log = stream.read()
		assert "www.uib.de" in log