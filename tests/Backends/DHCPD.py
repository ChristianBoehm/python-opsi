#!/usr/bin/env python
#-*- coding: utf-8 -*-

from __future__ import absolute_import

import codecs
import os
import tempfile

from OPSI.Util.File import DHCPDConfFile
from . import BackendMixin


class DHCPDConfMixin(BackendMixin):
    def setUpDHCPDConf(self):
        testData = '''
ddns-update-style none;
default-lease-time 68400;
# max-lease-time 68400;
max-lease-time 68400;
authoritative ;
log-facility local7;
use-host-decl-names on;
option domain-name "domain.local";
option domain-name-servers ns.domain.local;
option routers 192.168.99.254;

# Comment netbios name servers
option netbios-name-servers 192.168.99.2;

subnet 192.168.99.0 netmask 255.255.255.0 {
        group {
                #  Opsi hosts
                       next-server 192.168.99.2;
                filename "linux/pxelinux.0/xxx?{}";
                host opsi-test {
                                    hardware ethernet 9a:e5:3c:10:22:22;
                        fixed-address opsi-test.domain.local;
                }
    }
    host out-of-group {
        hardware ethernet 9a:e5:3c:10:22:22;
        fixed-address out-of-group.domain.local;
    }
}
host out-of-subnet {
    hardware ethernet 1a:25:31:11:23:21;
    fixed-address out-of-subnet.domain.local;
}
'''

        self.dhcpdConfFile = tempfile.mkstemp()[1]

        with codecs.open(self.dhcpdConfFile, 'w', 'utf-8') as f:
            f.write(testData)

        self.dhcpdConf = DHCPDConfFile(self.dhcpdConfFile)

    def tearDownDHCPDConf(self):
        del self.dhcpdConf

        if os.path.exists(self.dhcpdConfFile):
            os.remove(self.dhcpdConfFile)

        del self.dhcpdConfFile
