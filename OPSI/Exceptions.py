# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
OPSI Exceptions.
"""

from OPSI.Types import forceUnicode


__all__ = (
	'BackendAuthenticationError', 'BackendBadValueError',
	'BackendConfigurationError', 'BackendError', 'BackendIOError',
	'BackendMissingDataError', 'BackendModuleDisabledError',
	'BackendPermissionDeniedError', 'BackendReferentialIntegrityError',
	'BackendTemporaryError', 'BackendUnableToConnectError',
	'BackendUnaccomplishableError',
	'CanceledException', 'LicenseConfigurationError', 'LicenseMissingError',
	'OpsiAuthenticationError', 'OpsiBackupBackendNotFound',
	'OpsiBackupFileError', 'OpsiBackupFileNotFound', 'OpsiBadRpcError',
	'OpsiConnectionError', 'OpsiError', 'OpsiProductOrderingError',
	'OpsiRpcError', 'OpsiServiceVerificationError', 'OpsiTimeoutError',
	'RepositoryError',
)


class OpsiError(Exception):
	""" Base class for OPSI Backend exceptions. """

	ExceptionShortDescription = "Opsi error"

	def __init__(self, message=''):
		super().__init__(message)
		self.message = forceUnicode(message)

	def __str__(self):
		if self.message:
			return u"%s: %s" % (self.ExceptionShortDescription, self.message)
		else:
			return u"%s" % self.ExceptionShortDescription

	def __repr__(self):
		if self.message:
			text = u"<{0}({1!r})>".format(self.__class__.__name__, self.message)
		else:
			text = u"<{0}()>".format(self.__class__.__name__)

		return text


class OpsiBackupFileError(OpsiError):
	ExceptionShortDescription = u"Opsi backup file error"


class OpsiBackupFileNotFound(OpsiBackupFileError):
	ExceptionShortDescription = u"Opsi backup file not found"


class OpsiBackupBackendNotFound(OpsiBackupFileError):
	ExceptionShortDescription = u"Opsi backend not found in backup"


class OpsiAuthenticationError(OpsiError):
	ExceptionShortDescription = u"Opsi authentication error"


class OpsiServiceVerificationError(OpsiError):
	ExceptionShortDescription = u"Opsi service verification error"


class OpsiBadRpcError(OpsiError):
	ExceptionShortDescription = u"Opsi bad rpc error"


class OpsiRpcError(OpsiError):
	ExceptionShortDescription = u"Opsi rpc error"


class OpsiConnectionError(OpsiError):
	ExceptionShortDescription = u"Opsi connection error"


class OpsiTimeoutError(OpsiError):
	ExceptionShortDescription = u"Opsi timeout error"


class OpsiProductOrderingError(OpsiError):
	ExceptionShortDescription = u"A condition for ordering cannot be fulfilled"

	def __init__(self, message='', problematicRequirements=None):
		super().__init__(message)

		self.problematicRequirements = problematicRequirements or []

	def __repr__(self):
		if self.message:
			text = u"<{0}({1!r}, {2!r})>".format(self.__class__.__name__, self.message, self.problematicRequirements)
		else:
			text = u"<{0}()>".format(self.__class__.__name__)

		return text

	def __str__(self):
		if self.message:
			if self.problematicRequirements:
				return u"{0}: {1} ({2})".format(self.ExceptionShortDescription, self.message, self.problematicRequirements)
			else:
				return u"{0}: {1}".format(self.ExceptionShortDescription, self.message)
		else:
			return forceUnicode(self.ExceptionShortDescription)


class BackendError(OpsiError):
	""" Exception raised if there is an error in the backend. """
	ExceptionShortDescription = u"Backend error"


class BackendIOError(OpsiError):
	""" Exception raised if there is a read or write error in the backend. """
	ExceptionShortDescription = u"Backend I/O error"


class BackendUnableToConnectError(BackendIOError):
	"Exception raised if no connection can be established in the backend."
	ExceptionShortDescription = u"Backend I/O error"


class BackendConfigurationError(OpsiError):
	""" Exception raised if a configuration error occurs in the backend. """
	ExceptionShortDescription = u"Backend configuration error"


class BackendReferentialIntegrityError(OpsiError):
	"""
	Exception raised if there is a referential integration
	error occurs in the backend.
	"""
	ExceptionShortDescription = u"Backend referential integrity error"


class BackendBadValueError(OpsiError):
	""" Exception raised if a malformed value is found. """
	ExceptionShortDescription = u"Backend bad value error"


class BackendMissingDataError(OpsiError):
	""" Exception raised if expected data not found. """
	ExceptionShortDescription = u"Backend missing data error"


class BackendAuthenticationError(OpsiAuthenticationError):
	""" Exception raised if authentication failes. """
	ExceptionShortDescription = u"Backend authentication error"


class BackendPermissionDeniedError(OpsiError):
	""" Exception raised if a permission is denied. """
	ExceptionShortDescription = u"Backend permission denied error"


class BackendTemporaryError(OpsiError):
	""" Exception raised if a temporary error occurs. """
	ExceptionShortDescription = u"Backend temporary error"


class BackendUnaccomplishableError(OpsiError):
	"Exception raised if an unaccomplishable situation appears"

	ExceptionShortDescription = u"Backend unaccomplishable error"


class BackendModuleDisabledError(OpsiError):
	""" Exception raised if a needed module is disabled. """
	ExceptionShortDescription = u"Backend module disabled error"


class LicenseConfigurationError(OpsiError):
	"""
	Exception raised if a configuration error occurs in the license data base.
	"""
	ExceptionShortDescription = u"License configuration error"


class LicenseMissingError(OpsiError):
	""" Exception raised if a license is requested but cannot be found. """
	ExceptionShortDescription = u"License missing error"


class RepositoryError(OpsiError):
	ExceptionShortDescription = u"Repository error"


class CanceledException(Exception):
	ExceptionShortDescription = u"CanceledException"
