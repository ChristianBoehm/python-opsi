# -*- coding: utf-8 -*-

# Copyright (c) uib GmbH <info@uib.de>
# License: AGPL-3.0
"""
JSONRPC backend.

This backend executes the calls on a remote backend via JSONRPC.
"""

from __future__ import annotations

import warnings
from types import MethodType
from typing import Any
from urllib.parse import urlparse

from OPSI import __version__
from OPSI.Backend.Base import Backend
from opsicommon.client.opsiservice import ServiceClient, ServiceConnectionListener
from opsicommon.logging import get_logger

logger = get_logger("opsi.general")

__all__ = ("JSONRPCBackend",)


class JSONRPCBackend(Backend, ServiceConnectionListener):
	"""
	This Backend gives remote access to a Backend reachable via jsonrpc.
	"""
	def __init__(self, address: str, **kwargs: Any) -> None:  # pylint: disable=too-many-branches,too-many-statements
		"""
		Backend for JSON-RPC access to another opsi service.

		:param compression: Should requests be compressed?
		:type compression: bool
		"""

		self._name = "jsonrpc"

		Backend.__init__(self, **kwargs)  # type: ignore[misc]

		self.interface = []

		service_args = {
			"address": address,
			"user_agent": f"opsi-jsonrpc-backend/{__version__}",
			"verify": "accept_all"
		}
		for option, value in kwargs.items():
			option = option.lower().replace("_", "")
			if option == "username":
				service_args["username"] = str(value or "")
			elif option == "password":
				service_args["password"] = str(value or "")
			elif option == "cacertfile":
				if value not in (None, ""):
					service_args["ca_cert_file"] = str(value)
			elif option == "verifyservercert":
				if value:
					service_args["verify"] = ["opsi_ca", "uib_opsi_ca"]
				else:
					service_args["verify"] = "accept_all"
			elif option == "sessionid":
				if value:
					service_args["session_cookie"] = str(value)
			elif option == "sessionlifetime":
				if value:
					service_args["session_lifetime"] = int(value)
			elif option == "proxyurl":
				service_args["proxy_url"] = str(value) if value else None
			elif option == "application":
				service_args["user_agent"] = str(value)
			elif option == "connecttimeout":
				service_args["connect_timeout"] = int(value)

		self.service = ServiceClient(**service_args)
		self.service.register_connection_listener(self)

	@property
	def hostname(self) -> str:
		return urlparse(self.service.base_url).hostname

	def jsonrpc_getSessionId(self) -> str:  # pylint: disable=invalid-name
		return self.service.session_cookie

	def backend_exit(self) -> None:
		return self.service.disconnect()

	def connection_established(self, service_client: "ServiceClient") -> None:
		self.interface = self.service.jsonrpc("backend_getInterface")
		self._create_instance_methods()

	def backend_getInterface(self) -> list[dict[str, Any]]:  # pylint: disable=invalid-name
		return self.interface

	def _create_instance_methods(self) -> None:  # pylint: disable=too-many-locals
		for method in self.interface:
			try:
				method_name = method["name"]

				if method_name in (
					"backend_exit",
					"backend_getInterface",
					"jsonrpc_getSessionId",
				):
					continue

				logger.debug("Creating instance method: %s", method_name)

				args = method["args"]
				varargs = method["varargs"]
				keywords = method["keywords"]
				defaults = method["defaults"]

				arg_list = []
				call_list = []
				for i, argument in enumerate(args):
					if argument == "self":
						continue

					if isinstance(defaults, (tuple, list)) and len(defaults) + i >= len(args):
						default = defaults[len(defaults) - len(args) + i]
						if isinstance(default, str):
							default = "{0!r}".format(default).replace('"', "'")  # pylint: disable=consider-using-f-string
						arg_list.append(f"{argument}={default}")
					else:
						arg_list.append(argument)
					call_list.append(argument)

				if varargs:
					for vararg in varargs:
						arg_list.append(f"*{vararg}")
						call_list.append(vararg)

				if keywords:
					arg_list.append(f"**{keywords}")
					call_list.append(keywords)

				arg_string = ", ".join(arg_list)
				call_string = ", ".join(call_list)

				logger.trace("%s: arg string is: %s", method_name, arg_string)
				logger.trace("%s: call string is: %s", method_name, call_string)
				with warnings.catch_warnings():
					exec(  # pylint: disable=exec-used
						f'def {method_name}(self, {arg_string}): return self.execute_rpc("{method_name}", [{call_string}])'
					)
					setattr(self, method_name, MethodType(eval(method_name), self))  # pylint: disable=eval-used
			except Exception as err:  # pylint: disable=broad-except
				logger.error("Failed to create instance method '%s': %s", method, err, exc_info=True)
