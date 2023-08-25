# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
Backend Extender.

Reads the backend extensions and allows for them to be used like normal
methods in a backend context.
"""

from __future__ import absolute_import

import inspect
import os
import types
from functools import lru_cache

from opsicommon.logging import get_logger

import typing  # this is needed exec in __createExtensions  # pylint: disable=unused-import
from OPSI.Backend.Base import ExtendedBackend
from OPSI.Backend.Base.Extended import get_function_signature_and_args
from OPSI.Backend.Manager.AccessControl import BackendAccessControl
from OPSI.Exceptions import *  # this is needed for dynamic extension loading  # pylint: disable=wildcard-import,unused-wildcard-import
from OPSI.Exceptions import BackendConfigurationError
from OPSI.Object import *  # this is needed for dynamic extension loading  # pylint: disable=wildcard-import,unused-wildcard-import
from OPSI.Types import *  # this is needed for dynamic extension loading  # pylint: disable=wildcard-import,unused-wildcard-import
from OPSI.Util import (  # used in extensions  # pylint: disable=unused-import
	getfqdn,
	objectToBeautifiedText,
)

from .. import deprecated  # used in extensions  # pylint: disable=unused-import
from .Dispatcher import BackendDispatcher

__all__ = ("BackendExtender",)

logger = get_logger("opsi.general")


class BackendExtender(ExtendedBackend):
	def __init__(self, backend, **kwargs):
		if (
			not isinstance(backend, ExtendedBackend)
			and not isinstance(backend, BackendDispatcher)
			and not isinstance(backend, BackendAccessControl)
		):
			raise TypeError(
				"BackendExtender needs instance of ExtendedBackend , BackendDispatcher or BackendAccessControl"
				f" as backend, got {backend.__class__.__name__}"
			)

		ExtendedBackend.__init__(self, backend, **kwargs)

		self._extensionConfigDir = None
		self._extensionClass = None
		self._extensionReplaceMethods = True

		for option, value in kwargs.items():
			option = option.lower()
			if option == "extensionconfigdir":
				self._extensionConfigDir = value
			elif option == "extensionclass":
				self._extensionClass = value
			elif option == "extensionreplacemethods":
				self._extensionReplaceMethods = forceBool(value)

		self.__createExtensions()

	def __createExtensions(self):
		if self._extensionClass:
			for methodName, functionRef in inspect.getmembers(self._extensionClass, inspect.isfunction):
				if getattr(functionRef, "no_export", False):
					continue
				if methodName.startswith("_"):
					continue
				logger.trace("Extending %s with instancemethod: %s", self._backend.__class__.__name__, methodName)

				sig = get_function_signature_and_args(functionRef)[0]
				sig = "(self)" if sig == "()" else f"(self, {sig[1:]}"
				new_function = exec(f"def {methodName}{sig}: pass")  # pylint: disable=exec-used
				new_function = eval(methodName)  # pylint: disable=eval-used
				new_function.__code__ = functionRef.__code__
				setattr(self, methodName, types.MethodType(new_function, self))

		if self._extensionConfigDir:
			try:
				for confFile in _getExtensionFiles(self._extensionConfigDir):
					try:
						logger.info("Reading config file '%s'", confFile)
						exec(_readExtension(confFile))  # pylint: disable=exec-used
					except Exception as err:
						logger.error(err, exc_info=True)
						raise RuntimeError(f"Error reading file {confFile!r}: {err}") from err

					for key, val in locals().copy().items():
						if key == "backend_getLicensingInfo":
							raise RuntimeError(f"Error reading file {confFile!r}")
						if isinstance(val, types.FunctionType):  # TODO: find a better way
							if hasattr(self, key) and not self._extensionReplaceMethods:
								continue
							logger.trace("Extending %s with instancemethod: '%s'", self._backend.__class__.__name__, key)
							setattr(self, key, types.MethodType(val, self))
			except Exception as err:
				raise BackendConfigurationError(f"Failed to read extensions from '{self._extensionConfigDir}': {err}") from err


@lru_cache(maxsize=None)
def _getExtensionFiles(directory) -> list:
	if not os.path.exists(directory):
		raise OSError(f"No extensions loaded: extension directory {directory} does not exist")

	return [os.path.join(directory, filename) for filename in sorted(os.listdir(directory)) if filename.endswith(".conf")]


@lru_cache(maxsize=None)
def _readExtension(filepath):
	logger.debug("Reading extension file %s}", filepath)
	with open(filepath, encoding="utf-8") as confFileHandle:
		return confFileHandle.read()
