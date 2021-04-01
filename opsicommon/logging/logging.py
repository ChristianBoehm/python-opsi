# -*- coding: utf-8 -*-
"""
:copyright: uib GmbH <info@uib.de>
This file is part of opsi - https://www.opsi.org

:license: GNU Affero General Public License version 3
"""

import traceback
import sys
import logging
import warnings
import contextvars
from contextlib import contextmanager
from typing import Dict, Any
import colorlog

from .constants import (
	DEFAULT_COLORED_FORMAT, DEFAULT_FORMAT, DATETIME_FORMAT,
	LOG_COLORS, SECRET_REPLACEMENT_STRING
)
from ..utils import Singleton

logger = logging.getLogger()
context = contextvars.ContextVar('context', default={})

def secret(self, msg:str, *args, **kwargs):
	"""
	Logging with level SECRET.

	This method calls a log with level logging.SECRET.

	:param msg: Message to log (may contain %-style placeholders).
	:type msg: str
	:param *args: Arguments to fill %-style placeholders with.
	:param **kwargs: Additional keyword-arguments.
	"""
	if self.isEnabledFor(logging.SECRET):
		self._log(logging.SECRET, msg, args, **kwargs) # pylint: disable=protected-access

logging.Logger.secret = secret
logging.Logger.confidential = secret

def trace(self, msg, *args, **kwargs):
	"""
	Logging with level TRACE.

	This method calls a log with level logging.TRACE.

	:param msg: Message to log (may contain %-style placeholders).
	:type msg: str
	:param *args: Arguments to fill %-style placeholders with.
	:param **kwargs: Additional keyword-arguments.
	"""
	if self.isEnabledFor(logging.TRACE):
		self._log(logging.TRACE, msg, args, **kwargs) # pylint: disable=protected-access

logging.Logger.trace = trace
logging.Logger.debug2 = trace

def notice(self, msg, *args, **kwargs):
	"""
	Logging with level NOTICE.

	This method calls a log with level logging.NOTICE.

	:param msg: Message to log (may contain %-style placeholders).
	:type msg: str
	:param *args: Arguments to fill %-style placeholders with.
	:param **kwargs: Additional keyword-arguments.
	"""
	if self.isEnabledFor(logging.NOTICE):
		self._log(logging.NOTICE, msg, args, **kwargs) # pylint: disable=protected-access

logging.Logger.notice = notice

def essential(self, msg, *args, **kwargs):
	"""
	Logging with level ESSENTIAL.

	This method calls a log with level logging.ESSENTIAL.

	:param msg: Message to log (may contain %-style placeholders).
	:type msg: str
	:param *args: Arguments to fill %-style placeholders with.
	:param **kwargs: Additional keyword-arguments.
	"""
	if self.isEnabledFor(logging.ESSENTIAL):
		self._log(logging.ESSENTIAL, msg, args, **kwargs) # pylint: disable=protected-access

logging.Logger.essential = essential
logging.Logger.comment = essential
logging.Logger.devel = essential

def logrecord_init(self, name, level, pathname, lineno, msg, args, exc_info, func=None, sinfo=None, **kwargs):  # pylint: disable=too-many-arguments
	"""
	New Constructor for LogRecord.

	This overloads the LogRecord constructor to also include the OpsiLogLevel.
	The reason is to have backwards compatibility.

	:param name: Name of the logger to feed.
	:param level: Log level of the message.
	:param pathname: Path of the running module.
	:param lineno: Line number of the call.
	:param msg: Message to log (may contain %-style placeholders).
	:param args: Arguments to fill %-style placeholders with.
	:param exc_info: Traceback information in case of exceptions.
	:param func: Name of the calling function.
	:param sinfo: Call stack information.
	:param **kwargs: Additional keyword-arguments.
	"""
	self.__init_orig__(name, level, pathname, lineno, msg, args, exc_info, func=func, sinfo=sinfo, **kwargs)
	self.opsilevel = logging.level_to_opsi_level.get(level, level)

logging.LogRecord.__init_orig__ = logging.LogRecord.__init__
logging.LogRecord.__init__ = logrecord_init

def handle_log_exception(exc: Exception, record: logging.LogRecord = None, log: bool = True):
	"""
	Handles an exception in logging process.

	This method prints an Exception message and traceback to stderr.

	:param exc: Exception to be logged.
	:type exc: Exception
	:param record: Log record where the exception occured.
	:type record: logging.LogRecord.
	:param log: If true, the Exception is also output by the logger. (Default: True)
	:type log: bool
	"""
	print("Logging error:", file=sys.stderr)
	traceback.print_exc(file=sys.stderr)
	if not log:
		return
	try:
		logger.error("Logging error: %s", exc, exc_info=True)
		if record:
			logger.error(record.__dict__)
			#logger.error(f"{record.msg} - {record.args}")
	except Exception: # pylint: disable=broad-except
		pass

class ContextFilter(logging.Filter, metaclass=Singleton):
	"""
	class ContextFilter

	This class implements a filter which modifies allows to store context
	for a single thread/task.
	"""
	def __init__(self, filter_dict: Dict=None):
		"""
		ContextFilter Constructor

		This constructor initializes a ContextFilter instance with an
		empty dictionary as context.

		:param filter_dict: Dictionary that must be present in record context
			in order to accept the LogRecord.
		:type filter_dict: Dict
		"""
		super().__init__()
		self.filter_dict = {}
		self.set_filter(filter_dict)

	def get_context(self) -> Dict:  # pylint: disable=no-self-use
		"""
		Returns context of current thread/task.

		This method requests the thread/task identifier,
		looks up the context stored for it and returns it.

		:returns: Context for currently active thread/task.
		:rtype: Dict
		"""
		return context.get()

	def set_filter(self, filter_dict: Dict = None):
		"""
		Sets a new filter dictionary.

		This method expectes a filter dictionary.
		Records are only allowed to pass if their context has a matching
		key-value entry. None means, every record can pass.

		:param filter_dict: Value that must be present in record context
			in order to accept the LogRecord.
		:type filter_dict: Dict
		"""
		if filter_dict is None:
			self.filter_dict = {}
			return
		if not isinstance(filter_dict, dict):
			raise ValueError("filter_dict must be a python dictionary")

		self.filter_dict = {}
		for (key, value) in filter_dict.items():
			if isinstance(value, list):
				self.filter_dict[key] = value
			else:
				self.filter_dict[key] = [value]

	def filter(self, record: logging.LogRecord) -> bool:
		"""
		Adds context to a LogRecord.

		This method is called by Logger._log and modifies LogRecords.
		It adds the context stored for the current thread/task to the namespace.
		If the records context conforms to the filter, it is passed on.

		:param record: LogRecord to add context to and to filter.
		:type record: LogRecord

		:returns: True, if the record conforms to the filter rules.
		:rtype: bool
		"""
		if not hasattr(record, "context"):
			record.context = context.get()
		for (filter_key, filter_values) in self.filter_dict.items():
			record_value = record.context.get(filter_key)
			# Filter out record if key not present or value not in filter values
			if record_value in (None, "") or record_value not in filter_values:
				return False
		return True


class ContextSecretFormatter(logging.Formatter):
	"""
	class ContextSecretFormatter

	This class fulfills two formatting tasks:
	1. It alters the LogRecord to also include a string representation of
		a context dictionary, which can be logged by specifying a log
		format which includes %(contextstring)s
	2. It can replace secret strings specified to a SecretFilter by a
		replacement string, thus censor passwords etc.
	"""
	def __init__(self, orig_formatter: logging.Formatter): # pylint: disable=super-init-not-called
		"""
		ContextSecretFormatter constructor

		This constructor initializes the encapsulated Formatter with
		either one given as parameter or a newly created default one.

		:param orig_formatter: Formatter to encapsulate (my be None).
		:type orig_formatter: logging.Formatter
		"""
		if orig_formatter is None:
			orig_formatter = logging.Formatter()
		self.orig_formatter = orig_formatter
		self.secret_filter_enabled = True

	def disable_filter(self):
		"""
		Disable the Secret Filter

		This method sets secret_filter_enabled to False such that on evaluating LogRecords,
		the List if secrets is disregarded on formatting.
		"""
		self.secret_filter_enabled = False

	def enable_filter(self):
		"""
		Enable the Secret Filter

		This method sets secret_filter_enabled to True such that on evaluating LogRecords,
		the List if secrets is consulted on formatting.
		"""
		self.secret_filter_enabled = True

	def format(self, record: logging.LogRecord) -> str:
		"""
		Formats a LogRecord.

		This method takes a LogRecord and formats it to produce
		an output string. If context is specified in the LogRecord
		it is used to produce a contextstring which is included in
		the log string if %(contextstring)s is specified in the format.

		:param record: LogRecord to format.
		:type record: logging.LogRecord

		:returns: The formatted log string.
		:rytpe: str
		"""
		if hasattr(record, "context"):
			current_context = record.context
			if isinstance(current_context, dict):
				values = current_context.values()
				record.contextstring = ",".join([str(x) for x in values])
			else:
				record.contextstring = ""
		else:
			record.contextstring = ""
		#record.contextstring = 	f"{record.contextstring:{CONTEXT_STRING_MIN_LENGTH}}"
		msg = self.orig_formatter.format(record)
		if not self.secret_filter_enabled:
			return msg

		for _secret in secret_filter.secrets:
			msg = msg.replace(_secret, SECRET_REPLACEMENT_STRING)
		return msg

	def __getattr__(self, attr) -> Any:
		"""
		Retrieves attribute from original formatter.

		This method expects an attribute and returns the valuefor this
		attribute being part of the original formatters namespace.

		:param attr: Any attribute requested from the original formatter.
		:type attr: str

		:returns: Current value of the attribute.
		:rtype: Any
		"""
		return getattr(self.orig_formatter, attr)

class SecretFilter(metaclass=Singleton):
	"""
	class SecretFilter

	This class implements functionality of maintaining a collection
	of secrets which can be used by the ContextSecretFormatter.
	"""
	def __init__(self, min_length: int = 6):
		"""
		SecretFilter constructor.

		This constructor initializes the minimal length of secrets.
		If no value is provided, the default is 6 (characters long).

		:param min_length: Minimal length of a secret string (Default: 6).
		:type min_length: int
		"""
		self._min_length = min_length
		self.secrets = []

	def _initialize_handlers(self):  # pylint: disable=no-self-use
		"""
		Assign ContextSecretFormatter to Handlers.

		This method iterates of all Handlers of the root logger.
		Each Handler is assigned a ContextSecretFormatter to ensure that
		no secret string is printed into a Log stream.
		"""
		for handler in logging.root.handlers:
			if not isinstance(handler.formatter, ContextSecretFormatter):
				handler.formatter = ContextSecretFormatter(handler.formatter)

	def set_min_length(self, min_length: int):
		"""
		Sets minimal secret length.

		This method assigns a new value to the minimal secret length.
		Any new secret string can only be added, if it has more characters.

		:param min_length: Minimal length of a secret string.
		:type min_length: int
		"""
		self._min_length = min_length

	def clear_secrets(self):
		"""
		Delete all secret strings.

		This method clears the list of secret strings.
		"""
		self.secrets = []

	def add_secrets(self, *secrets: str):
		"""
		Inserts new secret strings.

		This method expects any number of secret strings and adds them to the list.

		:param *secrets: Any number of strings (as individual arguments) to add.
		:type *secrets: str
		"""
		self._initialize_handlers()
		for _secret in secrets:
			if _secret and len(_secret) >= self._min_length and not _secret in self.secrets:
				self.secrets.append(_secret)

	def remove_secrets(self, *secrets: str):
		"""
		Removes secret strings.

		This method expects any number of secret strings and removes them from the list.

		:param *secrets: Any number of strings (as individual arguments) to remove.
		:type *secrets: str
		"""
		for _secret in secrets:
			if _secret in self.secrets:
				self.secrets.remove(_secret)

class ObservableHandler(logging.StreamHandler, metaclass=Singleton):
	def __init__(self):
		logging.StreamHandler.__init__(self)
		self._observers = []

	def attach_observer(self, observer):
		if observer not in self._observers:
			self._observers.append(observer)
	attachObserver = attach_observer

	def detach_observer(self, observer):
		if observer in self._observers:
			self._observers.remove(observer)
	detachObserver = detach_observer

	def emit(self, record):
		if self._observers:
			message = self.format(record)
			for observer in self._observers:
				try:
					observer.messageChanged(self, message)
				except Exception as err: # pylint: disable=broad-except
					handle_log_exception(err)

last_stderr_format = None # pylint: disable=invalid-name
last_file_format = None # pylint: disable=invalid-name
def logging_config( # pylint: disable=too-many-arguments,too-many-branches
	stderr_level: int = None,
	stderr_format: str = None,
	log_file: str = None,
	file_level: int = None,
	file_format: str = None,
	remove_handlers: bool = False
):
	"""
	Initialize logging.

	This method initializes the logger according to given parameters.
	Log levels and format for stderr and file output can be set individually.
	:param stderr_level: Loglevel to set for the stderr logging stream.
	:type stderr_level: int
	:param stderr_format: Format to set for the stderr logging stream.
	:type stderr_format: str
	:param log_file: Name of the file to write logging stream to.
	:type log_file: str
	:param file_level: Loglevel to set for the file logging stream.
	:type file_level: int
	:param file_format: Format to set for the file logging stream.
	:type file_format: str
	"""
	add_context_filter_to_loggers()

	global last_stderr_format # pylint: disable=global-statement,invalid-name
	if stderr_format is None:
		stderr_format = last_stderr_format or DEFAULT_FORMAT
	else:
		last_stderr_format = stderr_format

	global last_file_format # pylint: disable=global-statement,invalid-name
	if file_format is None:
		file_format = last_file_format or DEFAULT_FORMAT
	else:
		last_file_format = file_format

	if stderr_level is not None and stderr_level < 10:
		stderr_level = logging.opsi_level_to_level[stderr_level]
	if file_level is not None and file_level < 10:
		file_level = logging.opsi_level_to_level[file_level]

	if log_file:
		if remove_handlers:
			remove_all_handlers(handler_type=logging.FileHandler)
		else:
			remove_all_handlers(handler_name="opsi_file_handler")
		handler = logging.FileHandler(log_file, encoding="utf-8")
		handler.name = "opsi_file_handler"
		logging.root.addHandler(handler)
	if file_level is not None:
		for handler in get_all_handlers(logging.FileHandler):
			handler.setLevel(file_level)
	if stderr_level is not None:
		if remove_handlers:
			remove_all_handlers(handler_type=logging.StreamHandler)
		else:
			remove_all_handlers(handler_name="opsi_stderr_handler")
		if stderr_level != 0:
			handler = logging.StreamHandler(stream=sys.stderr)
			handler.name = "opsi_stderr_handler"
			logging.root.addHandler(handler)
		for handler in get_all_handlers(logging.StreamHandler):
			handler.setLevel(stderr_level)

	if not observable_handler in get_all_handlers(ObservableHandler):
		logging.root.addHandler(observable_handler)

	min_value = 0
	for handler in get_all_handlers():
		if handler.level != 0 and handler.level < min_value:
			min_value = handler.level
	logging.root.setLevel(min_value)

	if stderr_format and stderr_format.find("(log_color)") != -1 and not sys.stderr.isatty():
		stderr_format = stderr_format.replace('%(log_color)s', '').replace('%(reset)s', '')
	set_format(file_format, stderr_format)

def init_logging(
	stderr_level: int = None,
	stderr_format: str = None,
	log_file: str = None,
	file_level: int = None,
	file_format: str = None
):
	return logging_config(stderr_level, stderr_format, log_file, file_level, file_format, True)

def set_format(
	file_format: str = DEFAULT_FORMAT,
	stderr_format: str = DEFAULT_COLORED_FORMAT,
	datefmt: str = DATETIME_FORMAT,
	log_colors: Dict = None
):
	"""
	Assigns ContextSecretFormatter to all Handlers.

	This method takes optional arguments for format, dateformat and log colors
	and creates ContextSecretFormatters considering those.
	Every Handler is assigned such a ContextSecretFormatter.

	:param file_format: Format to set for the file logging stream.
	:type file_format: str
	:param stderr_format: Format to set for the stderr logging stream.
	:type stderr_format: str
	:param datefmt: Date format for logging. If omitted, a default dateformat is used.
	:type datefmt: str
	:param log_colors: Dictionary of colors for different log levels.
		If omitted, a default Color dictionary is used.
	:type log_colors: Dict
	"""
	for handler_type in (logging.StreamHandler, logging.FileHandler):
		for handler in get_all_handlers(handler_type):
			fmt = stderr_format if handler_type is logging.StreamHandler else file_format
			formatter = None
			if fmt.find("(log_color)") >= 0:
				formatter = colorlog.ColoredFormatter(fmt, datefmt=datefmt, log_colors=log_colors or LOG_COLORS)
			else:
				formatter = logging.Formatter(fmt, datefmt=datefmt)
			csformatter = ContextSecretFormatter(formatter)
			if handler.level == logging.SECRET:
				csformatter.disable_filter()
			handler.setFormatter(csformatter)

@contextmanager
def log_context(new_context: Dict):
	"""
	Contextmanager to set a context.

	This contextmanager sets context to the given one on entering
	and resets to the previous dictionary when leaving.

	:param new_context: new context to set for the section.
	:type new_context: dict
	"""
	try:
		token = set_context(new_context)
		yield
	finally:
		if token is not None:
			context.reset(token)

def set_context(new_context: Dict) -> contextvars.Token:
	"""
	Sets a context.

	This method sets context to the given one and returns a reset-token.

	:param new_context: new context to set.
	:type new_context: dict

	:returns: reset-token for the context (stores previous value).
	:rtype: contextvars.Token
	"""
	if isinstance(new_context, dict):
		return context.set(new_context)
	return None

def add_context_filter_to_loggers():
	for _logger in get_all_loggers():
		if not isinstance(_logger, logging.PlaceHolder):
			if not context_filter in _logger.filters:
				_logger.addFilter(context_filter)

def set_filter(filter_dict: Dict):
	"""
	Sets a new filter dictionary.

	This method expectes a filter dictionary.
	Records are only allowed to pass if their context contains
	this specific dictionary. None means, every record can pass.

	:param filter_dict: Dictionary that must be present in record
		context in order to accept the LogRecord.
	:type filter_dict: Dict
	"""
	add_context_filter_to_loggers()
	context_filter.set_filter(filter_dict)

def set_filter_from_string(filter_string: str):
	"""
	Parses string and sets filter dictionary.

	This method expects a string (e.g. from user input).
	It is parsed to create a dictionary which is set as filter dictionary.
	The parsing rules are:
		*	Entries are separated by ';'.
		*	One entry consists of exactly two strings separated by '='.
		*	The first one is interpreted as key, the second as value(s).
		*	Values of the same key are separated by ','.

	:param filter_string: String to parse for a filter statement.
	:type filter_string: str
	"""
	filter_dict = {}
	if filter_string is None:
		set_filter(None)
		return
	if isinstance(filter_string, str):
		filter_string = filter_string.split(";")
	if not isinstance(filter_string, list):
		raise ValueError("filter_string must be either string or list")
	for part in filter_string:
		entry = part.split("=")
		if len(entry) == 2:
			key = entry[0].strip()
			values = entry[1].split(",")
			filter_dict[key] = [v.strip() for v in values]
	set_filter(filter_dict)

def get_all_loggers():
	"""
	Gets list of all loggers.

	This method requests all Logger instances registered at
	logging.Logger.manager.loggerDict and returns them as a list.

	:returns: List containing all loggers (including root)
	:rtype: List
	"""
	return [logging.root] + list(logging.Logger.manager.loggerDict.values())

def get_all_handlers(handler_type: type = None, handler_name: str = None):
	"""
	Gets list of all handlers.

	This method iterates over all registered loggers. All handlers
	(optional: of a certain type) are collected and returned as list.

	:param handler_type: If not None, return only handlers of specified type.
	:type handler_type: class

	:returns: List containing all handlers (of specified type) of all loggers.
	:rtype: List
	"""
	handlers = []
	for _logger in get_all_loggers():
		if not isinstance(_logger, logging.PlaceHolder):
			for _handler in _logger.handlers:
				if (
					(not handler_type or type(_handler) == handler_type) and  # exact type needed, not subclass pylint: disable=unidiomatic-typecheck
					(not handler_name or _handler.name == handler_name)
				):
					handlers.append(_handler)
	return handlers

def remove_all_handlers(handler_type: type = None, handler_name: str = None):
	"""
	Removes all handlers (of a certain type).

	This method iterates over all loggers. All assigned handlers
	(of a given type or all) are removed.

	:param handler_type: Type of handlers that should be removed.
	:type handler_type: class
	"""
	for _logger in get_all_loggers():
		if not isinstance(_logger, logging.PlaceHolder):
			for _handler in _logger.handlers:
				if (
					(not handler_type or type(_handler) == handler_type) and  # exact type needed, not subclass pylint: disable=unidiomatic-typecheck
					(not handler_name or _handler.name == handler_name)
				):
					_logger.removeHandler(_handler)

def print_logger_info():
	"""
	Debug output logger status.

	This method prints all loggers with their respective
	handlers and formatters to stdout.
	"""
	for _logger in get_all_loggers():
		print(f"- Logger: {_logger}", file=sys.stderr)
		if not isinstance(_logger, logging.PlaceHolder):
			for _filter in _logger.filters:
				print(f"  - Filter: {_filter} ", file=sys.stderr)
			for _handler in _logger.handlers:
				name = str(_handler)
				if _handler.name:
					tmp = name.split(" ")
					tmp.insert(1, f'"{_handler.name}"')
					name = " ".join(tmp)
				print(f"  - Handler: {name} ", file=sys.stderr)
				print(f"    - Formatter: {_handler.formatter}", file=sys.stderr)

def _log_warning(message, category, filename, lineno, line=None, file=None): # pylint: disable=unused-argument,too-many-arguments
	logger.warning("Warning '%s' in file '%s', line %s", message, filename, lineno)
	for entry in traceback.format_stack():
		for _line in entry.split("\n"):
			logger.debug(_line)
warnings.showwarning = _log_warning

observable_handler = ObservableHandler()
secret_filter = SecretFilter()
context_filter = ContextFilter()
logging_config(stderr_level=logging.WARNING)
