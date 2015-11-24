#!/usr/bin/env python
#-*- coding: utf-8 -*-

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
Testing the backend configuration.

:author: Niko Wenselowski <n.wenselowski@uib.de>
:license: GNU Affero General Public License version 3
"""

from __future__ import absolute_import

import os
import shutil
import unittest
from contextlib import contextmanager

import mock

from OPSI.Util import md5sum
from OPSI.Util.Task.ConfigureBackend.DHCPD import configureDHCPD

from .helpers import workInTemporaryDirectory

FAKE_RESTART_COMMAND = 'service opsi-test-dhcpd restart'

@contextmanager
def disableSystemCallsForConfigureDHCPD():
    with mock.patch('OPSI.Util.Task.ConfigureBackend.DHCPD.pwd.getpwnam', lambda x: (0, 0, 1234)):
        with mock.patch('OPSI.Util.Task.ConfigureBackend.DHCPD.grp.getgrnam', lambda x: (0, 0, 5678)):
            with mock.patch('OPSI.Util.Task.ConfigureBackend.DHCPD.execute'):
                with mock.patch('OPSI.Util.Task.ConfigureBackend.DHCPD.patchSudoersFileToAllowRestartingDHCPD'):

                    def getFakeRestartCommand(default=None):
                        return FAKE_RESTART_COMMAND

                    with mock.patch('OPSI.Util.Task.ConfigureBackend.DHCPD.getDHCPDRestartCommand', getFakeRestartCommand):
                        with mock.patch('OPSI.Util.Task.ConfigureBackend.DHCPD.os.chown'):
                            with mock.patch('OPSI.Util.Task.ConfigureBackend.DHCPD.os.chmod'):
                                yield


class ConfigureDHCPDTestCase(unittest.TestCase):
    def testJustExitingIfFileDoesNotExist(self):
        with workInTemporaryDirectory() as tempDir:
            configureDHCPD('not.here')

    def testNextServer(self):
        with workInTemporaryDirectory() as tempDir:
            targetFile = os.path.join(tempDir, 'dhcpd_1.conf')

            with open(targetFile, 'w') as target:
                target.write("""
use-host-decl-names on;
subnet 192.168.0.0 netmask 255.255.0.0 {
    group {
        filename "linux/pxelinux.0";
        host bh-win7 {
            fixed-address 192.168.20.81;
            hardware ethernet 52:54:00:29:23:16;
        }
    }
}
""")

            with disableSystemCallsForConfigureDHCPD():
                configureDHCPD(targetFile)

            found = False
            with open(targetFile) as target:
                for line in target:
                    if "next-server" in line:
                        found = True
                        break

            self.assertTrue(found, "next-server not fonud in new file.")

    def testConfiguringEmptyFile(self):
        with workInTemporaryDirectory() as tempDir:
            filename = 'dhcpd_test.conf'
            with open(filename, 'wx'):
                pass

            oldHash = md5sum(filename)

            with disableSystemCallsForConfigureDHCPD():
                configureDHCPD(filename)

            newHash = md5sum(filename)

            self.assertNotEquals(oldHash, newHash)


if __name__ == '__main__':
    unittest.main()
