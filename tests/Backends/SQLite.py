#! /usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright (C) 2013-2015 uib GmbH
#
# http://www.uib.de/
#
# All rights reserved.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import absolute_import

from contextlib import contextmanager

from OPSI.Backend.SQLite import SQLiteBackend, SQLiteObjectBackendModificationTracker
from OPSI.Backend.Backend import ExtendedConfigDataBackend
from . import BackendMixin
from ..helpers import workInTemporaryDirectory

try:
    from .config import SQLiteconfiguration
except ImportError:
    SQLiteconfiguration = {}


class SQLiteBackendMixin(BackendMixin):

    CREATES_INVENTORY_HISTORY = True

    def setUpBackend(self):
        self.backend = ExtendedConfigDataBackend(SQLiteBackend(**SQLiteconfiguration))
        self.backend.backend_createBase()

    def tearDownBackend(self):
        self.backend.backend_deleteBase()


@contextmanager
def getSQLiteBackend(configuration=None):
	# Defaults and settings from the old fixture.
	# defaultOptions = {
	# 	'processProductPriorities':            True,
	# 	'processProductDependencies':          True,
	# 	'addProductOnClientDefaults':          True,
	# 	'addProductPropertyStateDefaults':     True,
	# 	'addConfigStateDefaults':              True,
	# 	'deleteConfigStateIfDefault':          True,
	# 	'returnObjectsOnUpdateAndCreate':      False
	# }
	# licenseManagement = True

	if configuration is None:
		configuration = SQLiteconfiguration

	backend = SQLiteBackend(**SQLiteconfiguration)
	backend.backend_createBase()
	yield backend
	backend.backend_deleteBase()


@contextmanager
def getSQLiteModificationTracker(database=":memory:"):
	if not database:
		with workInTemporaryDirectory() as tempDir:
			database = os.path.join(tempDir, "tracker.sqlite")
			yield SQLiteObjectBackendModificationTracker(database=database)
	else:
		yield SQLiteObjectBackendModificationTracker(database=database)
