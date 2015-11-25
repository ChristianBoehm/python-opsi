#!/usr/bin/env python
#-*- coding: utf-8 -*-

# This file is part of python-opsi.
# Copyright (C) 2013-2015 uib GmbH <info@uib.de>

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
Backend mixin for testing software / hardware audit functionality.

:author: Niko Wenselowski <n.wenselowski@uib.de>
:license: GNU Affero General Public License version 3
"""

from __future__ import absolute_import

from OPSI.Object import (AuditSoftware, AuditSoftwareOnClient,
    AuditHardware, AuditHardwareOnHost, AuditSoftwareToLicensePool)

from .Clients import ClientsMixin
from .Products import getLocalbootProducts, ProductsMixin
from .Licenses import LicensesMixin


def getAuditHardwares():
    auditHardware1 = AuditHardware(
        hardwareClass='COMPUTER_SYSTEM',
        description='a pc',
        vendor='Dell',
        model='xyz',
    )

    auditHardware2 = AuditHardware(
        hardwareClass='COMPUTER_SYSTEM',
        description=None,
        vendor='HP',
        model='0815',
    )

    auditHardware3 = AuditHardware(
        hardwareClass='BASE_BOARD',
        name='MSI 2442',
        description='AMD motherboard',
        vendor='MSI',
        model='äüöüöäüöüäüööüö11',
        product=None
    )

    auditHardware4 = AuditHardware(
        hardwareClass='CHASSIS',
        name='Manufacturer XX-112',
        description='A chassis',
        chassisType='Desktop'
    )

    return auditHardware1, auditHardware2, auditHardware3, auditHardware4


def getAuditSoftwares(product=None):
    auditSoftware1 = AuditSoftware(
        name='A software',
        version='1.0.21',
        subVersion='',
        language='',
        architecture='',
        windowsSoftwareId='{480aa013-93a7-488c-89c3-b985b6c8440a}',
        windowsDisplayName='A Software',
        windowsDisplayVersion='1.0.21',
        installSize=129012992
    )

    if product is None:
        product = getLocalbootProducts()[0]

    auditSoftware2 = AuditSoftware(
        name=product.getName(),
        version=product.getProductVersion(),
        subVersion='',
        language='de',
        architecture='x64',
        windowsSoftwareId=product.getWindowsSoftwareIds()[0],
        windowsDisplayName=product.getName(),
        windowsDisplayVersion=product.getProductVersion(),
        installSize=217365267
    )

    auditSoftware3 = AuditSoftware(
        name='my software',
        version='',
        subVersion='12;00;01',
        language='',
        architecture='',
        windowsSoftwareId='my software',
        windowsDisplayName='',
        windowsDisplayVersion='',
        installSize=-1
    )

    auditSoftware4 = AuditSoftware(
        name='söftwäre\n;?&%$$$§$§§$$$§$',
        version=u'\\0012',
        subVersion='\n',
        language='de',
        architecture='',
        windowsSoftwareId='söftwäre\n;?&%$$$§$§§$$$§$',
        windowsDisplayName='söftwäre\n;?&%$$$§$§§$$$§$',
        windowsDisplayVersion='\n\r',
        installSize=-1
    )

    return auditSoftware1, auditSoftware2, auditSoftware3, auditSoftware4


def getAuditSoftwareOnClient(auditSoftwares, clients):
    auditSoftware1, auditSoftware2, auditSoftware3 = auditSoftwares[:3]
    client1, client2 = clients[:2]

    auditSoftwareOnClient1 = AuditSoftwareOnClient(
        name=auditSoftware1.getName(),
        version=auditSoftware1.getVersion(),
        subVersion=auditSoftware1.getSubVersion(),
        language=auditSoftware1.getLanguage(),
        architecture=auditSoftware1.getArchitecture(),
        clientId=client1.getId(),
        uninstallString='c:\\programme\\a software\\unistall.exe /S',
        binaryName=u'',
        firstseen=None,
        lastseen=None,
        state=None,
        usageFrequency=2,
        lastUsed='2009-02-12 09:48:22'
    )

    auditSoftwareOnClient2 = AuditSoftwareOnClient(
        name=auditSoftware2.getName(),
        version=auditSoftware2.getVersion(),
        subVersion=auditSoftware2.getSubVersion(),
        language=auditSoftware2.getLanguage(),
        architecture=auditSoftware2.getArchitecture(),
        clientId=client1.getId(),
        uninstallString='msiexec /x %s' % auditSoftware2.getWindowsSoftwareId(),
        binaryName=u'',
        firstseen=None,
        lastseen=None,
        state=None,
        usageFrequency=None,
        lastUsed=None
    )

    auditSoftwareOnClient3 = AuditSoftwareOnClient(
        name=auditSoftware3.getName(),
        version=auditSoftware3.getVersion(),
        subVersion=auditSoftware3.getSubVersion(),
        language=auditSoftware3.getLanguage(),
        architecture=auditSoftware3.getArchitecture(),
        clientId=client1.getId(),
        uninstallString=None,
        firstseen=None,
        lastseen=None,
        state=None,
        usageFrequency=0,
        lastUsed='2009-08-01 14:11:00'
    )

    auditSoftwareOnClient4 = AuditSoftwareOnClient(
        name=auditSoftware2.getName(),
        version=auditSoftware2.getVersion(),
        subVersion=auditSoftware2.getSubVersion(),
        language=auditSoftware2.getLanguage(),
        architecture=auditSoftware2.getArchitecture(),
        clientId=client2.getId(),
        firstseen=None,
        lastseen=None,
        state=None,
        usageFrequency=0,
        lastUsed=None
    )

    return auditSoftwareOnClient1, auditSoftwareOnClient2, auditSoftwareOnClient3, auditSoftwareOnClient4


def getAuditHardwareOnHost(auditHardwares, clients):
    auditHardware1, auditHardware2, auditHardware3 = auditHardwares[:3]
    client1, client2, client3 = clients[:3]

    auditHardwareOnHost1 = AuditHardwareOnHost(
        hostId=client1.getId(),
        hardwareClass='COMPUTER_SYSTEM',
        description=auditHardware1.description,
        vendor=auditHardware1.vendor,
        model=auditHardware1.model,
        serialNumber='843391034-2192',
        systemType='Desktop',
        totalPhysicalMemory=1073741824
    )

    auditHardwareOnHost2 = AuditHardwareOnHost(
        hostId=client2.getId(),
        hardwareClass='COMPUTER_SYSTEM',
        description=auditHardware1.description,
        vendor=auditHardware1.vendor,
        model=auditHardware1.model,
        serialNumber='142343234-9571',
        systemType='Desktop',
        totalPhysicalMemory=1073741824
    )

    auditHardwareOnHost3 = AuditHardwareOnHost(
        hostId=client3.getId(),
        hardwareClass='COMPUTER_SYSTEM',
        description=auditHardware2.description,
        vendor=auditHardware2.vendor,
        model=auditHardware2.model,
        serialNumber='a63c09dd234a213',
        systemType=None,
        totalPhysicalMemory=536870912
    )

    auditHardwareOnHost4 = AuditHardwareOnHost(
        hostId=client1.getId(),
        hardwareClass='BASE_BOARD',
        name=auditHardware3.name,
        description=auditHardware3.description,
        vendor=auditHardware3.vendor,
        model=auditHardware3.model,
        product=auditHardware3.product,
        serialNumber='xxxx-asjdks-sll3kf03-828112'
    )

    auditHardwareOnHost5 = AuditHardwareOnHost(
        hostId=client2.getId(),
        hardwareClass='BASE_BOARD',
        name=auditHardware3.name,
        description=auditHardware3.description,
        vendor=auditHardware3.vendor,
        model=auditHardware3.model,
        product=auditHardware3.product,
        serialNumber='xxxx-asjdks-sll3kf03-213791'
    )

    auditHardwareOnHost6 = AuditHardwareOnHost(
        hostId=client3.getId(),
        hardwareClass='BASE_BOARD',
        name=auditHardware3.name,
        description=auditHardware3.description,
        vendor=auditHardware3.vendor,
        model=auditHardware3.model,
        product=auditHardware3.product,
        serialNumber='xxxx-asjdks-sll3kf03-132290'
    )

    return (auditHardwareOnHost1, auditHardwareOnHost2, auditHardwareOnHost3,
            auditHardwareOnHost4, auditHardwareOnHost5, auditHardwareOnHost6)


class AuditSoftwareMixin(ProductsMixin):
    def setUpAuditSoftwares(self):
        self.setUpProducts()

        (self.auditSoftware1, self.auditSoftware2, self.auditSoftware3,
         self.auditSoftware4) = getAuditSoftwares(self.product2)

        self.auditSoftwares = [
            self.auditSoftware1, self.auditSoftware2, self.auditSoftware3,
            self.auditSoftware4
        ]

    def setUpAuditSoftwareToLicensePools(self):
        self.setUpLicensePool()

        self.auditSoftwareToLicensePool1 = AuditSoftwareToLicensePool(
            name=self.auditSoftware1.name,
            version=self.auditSoftware1.version,
            subVersion=self.auditSoftware1.subVersion,
            language=self.auditSoftware1.language,
            architecture=self.auditSoftware1.architecture,
            licensePoolId=self.licensePool1.id
        )

        self.auditSoftwareToLicensePool2 = AuditSoftwareToLicensePool(
            name=self.auditSoftware2.name,
            version=self.auditSoftware2.version,
            subVersion=self.auditSoftware2.subVersion,
            language=self.auditSoftware2.language,
            architecture=self.auditSoftware2.architecture,
            licensePoolId=self.licensePool2.id
        )

        self.auditSoftwareToLicensePools = [
            self.auditSoftwareToLicensePool1, self.auditSoftwareToLicensePool2
        ]

    def setUpAuditSoftwareOnClients(self):
        self.setUpAuditSoftwares()
        self.setUpClients()

        (self.auditSoftwareOnClient1, self.auditSoftwareOnClient2,
         self.auditSoftwareOnClient3, self.auditSoftwareOnClient4) = getAuditSoftwareOnClient(self.auditSoftwares, self.clients)

        self.auditSoftwareOnClients = [
            self.auditSoftwareOnClient1, self.auditSoftwareOnClient2,
            self.auditSoftwareOnClient3, self.auditSoftwareOnClient4
        ]


class AuditHardwareMixin(ClientsMixin):
    def setUpAuditHardwares(self):
        (self.auditHardware1, self.auditHardware2,
         self.auditHardware3, self.auditHardware4) = getAuditHardwares()

        self.auditHardwares = [self.auditHardware1, self.auditHardware2,
                               self.auditHardware3, self.auditHardware4]

    def setUpAuditHardwareOnHosts(self):
        self.setUpClients()
        self.setUpAuditHardwares()

        (self.auditHardwareOnHost1, self.auditHardwareOnHost2,
        self.auditHardwareOnHost3, self.auditHardwareOnHost4,
        self.auditHardwareOnHost5, self.auditHardwareOnHost6) = getAuditHardwareOnHost(self.auditHardwares, self.clients)

        self.auditHardwareOnHosts = [
            self.auditHardwareOnHost1, self.auditHardwareOnHost2,
            self.auditHardwareOnHost3, self.auditHardwareOnHost4,
            self.auditHardwareOnHost5, self.auditHardwareOnHost6
        ]

class AuditTestsMixin(AuditHardwareMixin, AuditSoftwareMixin):
    def testInventoryObjectMethods(self, licenseManagementBackend=False):
        # AuditSoftwares
        print(u"Testing auditSoftware methods")
        self.setUpAuditSoftwares()

        self.backend.auditSoftware_createObjects(self.auditSoftwares)

        auditSoftwares = self.backend.auditSoftware_getObjects()
        assert len(auditSoftwares) == len(self.auditSoftwares), u"got: '%s', expected: '%s'" % (
            auditSoftwares, len(self.auditSoftwares))

        auditSoftware3update = AuditSoftware(
            name=self.auditSoftware3.name,
            version=self.auditSoftware3.version,
            subVersion=self.auditSoftware3.subVersion,
            language=self.auditSoftware3.language,
            architecture=self.auditSoftware3.architecture,
            windowsSoftwareId=self.auditSoftware3.windowsSoftwareId,
            windowsDisplayName='updatedDN',
            windowsDisplayVersion=self.auditSoftware3.windowsDisplayVersion,
            installSize=self.auditSoftware3.installSize
        )

        self.backend.auditSoftware_updateObject(auditSoftware3update)
        auditSoftwares = self.backend.auditSoftware_getObjects(
            windowsDisplayName='updatedDN')
        assert len(auditSoftwares) == 1, u"got: '%s', expected: '%s'" % (
            auditSoftwares, 1)

        self.backend.auditSoftware_deleteObjects(self.auditSoftware3)
        auditSoftwares = self.backend.auditSoftware_getObjects()
        assert len(auditSoftwares) == len(self.auditSoftwares) - \
            1, u"got: '%s', expected: '%s'" % (
                auditSoftwares, len(self.auditSoftwares) - 1)

        self.backend.auditSoftware_insertObject(self.auditSoftware3)
        auditSoftwares = self.backend.auditSoftware_getObjects()
        assert len(auditSoftwares) == len(self.auditSoftwares), u"got: '%s', expected: '%s'" % (
            auditSoftwares, len(self.auditSoftwares))

        if (licenseManagementBackend):
            # TODO: this
            # AuditSoftwareToLicensePools
            print(u"Testing AuditSoftwareToLicensePool methods")
            self.backend.auditSoftwareToLicensePool_createObjects(
                self.auditSoftwareToLicensePools)

            auditSoftwareToLicensePools = self.backend.auditSoftwareToLicensePool_getObjects(
            )
            assert len(auditSoftwareToLicensePools) == len(self.auditSoftwareToLicensePools), u"got: '%s', expected: '%s'" % (
                auditSoftwareToLicensePools, len(self.auditSoftwareToLicensePools))

    def testAuditSoftwareOnClientsMethods(self):
        # AuditSoftwareOnClients
        print(u"Testing auditSoftwareOnClient methods")

        self.setUpAuditSoftwareOnClients()

        self.backend.auditSoftwareOnClient_createObjects(
            self.auditSoftwareOnClients)

        auditSoftwareOnClients = self.backend.auditSoftwareOnClient_getObjects(
        )
        assert len(auditSoftwareOnClients) == len(self.auditSoftwareOnClients), u"got: '%s', expected: '%s'" % (
            auditSoftwareOnClients, len(self.auditSoftwareOnClients))

        auditSoftwareOnClient1update = AuditSoftwareOnClient(
            name=self.auditSoftware1.getName(),
            version=self.auditSoftware1.getVersion(),
            subVersion=self.auditSoftware1.getSubVersion(),
            language=self.auditSoftware1.getLanguage(),
            architecture=self.auditSoftware1.getArchitecture(),
            clientId=self.client1.getId(),
            uninstallString=None,
            binaryName='updatedBN',
            firstseen=None,
            lastseen=None,
            state=None,
            usageFrequency=2,
            lastUsed='2009-02-12 09:48:22'
        )

        self.backend.auditSoftwareOnClient_updateObject(
            auditSoftwareOnClient1update)
        auditSoftwareOnClients = self.backend.auditSoftwareOnClient_getObjects(
            binaryName='updatedBN')
        assert len(auditSoftwareOnClients) == 1, u"got: '%s', expected: '%s'" % (
            auditSoftwareOnClients, 1)

        print(u"Deleting auditSoftwareOnClient: %s" %
                    auditSoftwareOnClient1update.toHash())
        self.backend.auditSoftwareOnClient_deleteObjects(
            auditSoftwareOnClient1update)
        auditSoftwareOnClients = self.backend.auditSoftwareOnClient_getObjects(
        )
        assert len(auditSoftwareOnClients) == len(self.auditSoftwareOnClients) - \
            1, u"got: '%s', expected: '%s'" % (
                auditSoftwareOnClients, len(self.auditSoftwareOnClients) - 1)

        self.backend.auditSoftwareOnClient_insertObject(
            self.auditSoftwareOnClient1)
        auditSoftwareOnClients = self.backend.auditSoftwareOnClient_getObjects(
        )
        assert len(auditSoftwareOnClients) == len(self.auditSoftwareOnClients), u"got: '%s', expected: '%s'" % (
            auditSoftwareOnClients, len(self.auditSoftwareOnClients))

        # AuditHardwares
        print(u"Testing auditHardware methods")
        self.setUpAuditHardwares()

        self.backend.auditHardware_createObjects(self.auditHardwares)

        auditHardwares = self.backend.auditHardware_getObjects()
        assert len(auditHardwares) == len(self.auditHardwares), u"got: '%s', expected: '%s'" % (
            auditHardwares, len(self.auditHardwares))

        auditHardwares = self.backend.auditHardware_getObjects(
            hardwareClass=['CHASSIS', 'COMPUTER_SYSTEM'])
        for auditHardware in auditHardwares:
            assert auditHardware.getHardwareClass() in ['CHASSIS', 'COMPUTER_SYSTEM'], u"'%s' not in '%s'" % (
                auditHardware.getHardwareClass(), ['CHASSIS', 'COMPUTER_SYSTEM'])

        auditHardwares = self.backend.auditHardware_getObjects(
            hardwareClass=['CHA*IS', '*UTER_SYS*'])
        for auditHardware in auditHardwares:
            assert auditHardware.getHardwareClass() in ['CHASSIS', 'COMPUTER_SYSTEM'], u"'%s' not in '%s'" % (
                auditHardware.getHardwareClass(), ['CHASSIS', 'COMPUTER_SYSTEM'])

        self.backend.auditHardware_deleteObjects(
            [self.auditHardware1, self.auditHardware2])
        auditHardwares = self.backend.auditHardware_getObjects()
        assert len(auditHardwares) == len(self.auditHardwares) - \
            2, u"got: '%s', expected: '%s'" % (
                auditHardwares, len(self.auditHardwares) - 2)

        self.backend.auditHardware_updateObjects(
            [self.auditHardware1, self.auditHardware2])
        assert len(auditHardwares) == len(self.auditHardwares) - \
            2, u"got: '%s', expected: '%s'" % (
                auditHardwares, len(self.auditHardwares) - 2)

        self.backend.auditHardware_createObjects(self.auditHardwares)
        auditHardwares = self.backend.auditHardware_getObjects()
        assert len(auditHardwares) == len(self.auditHardwares), u"got: '%s', expected: '%s'" % (
            auditHardwares, len(self.auditHardwares))

        # self.backend.auditHardware_createObjects(self.auditHardwares)

    def testAuditHardwareOnHostMethods(self, licenseManagementBackend=False):
        # TODO: make it work with inventoryHistory also.
        # maybe create another setup method and then just change the assertions
        # depending on what is used.
        self.setUpAuditSoftwares()
        self.setUpAuditHardwareOnHosts()

        self.backend.auditHardwareOnHost_createObjects(self.auditHardwareOnHosts)
        auditHardwareOnHosts = self.backend.auditHardwareOnHost_getObjects()
        self.assertEqual(len(auditHardwareOnHosts), len(self.auditHardwareOnHosts),
            u"Expected {nexpected} but got {n}: {ahoh}".format(
                nexpected=len(auditHardwareOnHosts),
                n=len(self.auditHardwareOnHosts),
                ahoh=auditHardwareOnHosts
            )
        )

        auditHardwareOnHost4update = self.auditHardwareOnHost4.clone()
        auditHardwareOnHost4update.setLastseen('2000-01-01 01:01:01')
        self.backend.auditHardwareOnHost_insertObject(
            auditHardwareOnHost4update)
        auditHardwareOnHosts = self.backend.auditHardwareOnHost_getObjects()

        print('Using inventory history? {0}'.format(self.CREATES_INVENTORY_HISTORY))
        if self.CREATES_INVENTORY_HISTORY:
            self.assertEqual(
                len(self.auditHardwareOnHosts) + 1,
                len(auditHardwareOnHosts),
                'Expected {nexpected} but got {actual}: {items}'.format(
                    actual=len(auditHardwareOnHosts),
                    nexpected=len(self.auditHardwareOnHosts) + 1,
                    items=auditHardwareOnHosts
                )
            )
        else:
            self.assertEqual(
                len(self.auditHardwareOnHosts),
                len(auditHardwareOnHosts),
                'Expected {nexpected} but got {actual}: {items}'.format(
                    actual=len(auditHardwareOnHosts),
                    nexpected=len(self.auditHardwareOnHosts),
                    items=auditHardwareOnHosts
                )
            )

        auditHardwareOnHosts = self.backend.auditHardwareOnHost_getObjects(
            lastseen='2000-01-01 01:01:01')
        assert len(auditHardwareOnHosts) == 1, u"got: '%s', expected: '%s'" % (
            auditHardwareOnHosts, 1)

        auditHardwareOnHost4update.setState(0)
        self.backend.auditHardwareOnHost_insertObject(
            auditHardwareOnHost4update)
        auditHardwareOnHosts = self.backend.auditHardwareOnHost_getObjects()
        if self.CREATES_INVENTORY_HISTORY:
            assert len(auditHardwareOnHosts) == len(self.auditHardwareOnHosts) + \
                2, u"got: '%s', expected: '%s'" % (
                    auditHardwareOnHosts, len(self.auditHardwareOnHosts) + 2)
        else:
            assert len(auditHardwareOnHosts) == len(self.auditHardwareOnHosts), u"got: '%s', expected: '%s'" % (
                auditHardwareOnHosts, len(self.auditHardwareOnHosts))

        self.backend.auditHardwareOnHost_insertObject(
            auditHardwareOnHost4update)
        auditHardwareOnHosts = self.backend.auditHardwareOnHost_getObjects()
        if self.CREATES_INVENTORY_HISTORY:
            assert len(auditHardwareOnHosts) == len(self.auditHardwareOnHosts) + \
                2, u"got: '%s', expected: '%s'" % (
                    auditHardwareOnHosts, len(self.auditHardwareOnHosts) + 2)
        else:
            assert len(auditHardwareOnHosts) == len(self.auditHardwareOnHosts), u"got: '%s', expected: '%s'" % (
                auditHardwareOnHosts, len(self.auditHardwareOnHosts))

        auditHardwareOnHost4update.setLastseen(None)
        self.backend.auditHardwareOnHost_insertObject(
            auditHardwareOnHost4update)
        auditHardwareOnHosts = self.backend.auditHardwareOnHost_getObjects()
        if self.CREATES_INVENTORY_HISTORY:
            assert len(auditHardwareOnHosts) == len(self.auditHardwareOnHosts) + \
                3, u"got: '%s', expected: '%s'" % (
                    auditHardwareOnHosts, len(self.auditHardwareOnHosts) + 3)
        else:
            assert len(auditHardwareOnHosts) == len(self.auditHardwareOnHosts), u"got: '%s', expected: '%s'" % (
                auditHardwareOnHosts, len(self.auditHardwareOnHosts))

        self.backend.auditHardwareOnHost_delete(
            hostId=[], hardwareClass=[], firstseen=[], lastseen=[], state=[])
        auditHardwareOnHosts = self.backend.auditHardwareOnHost_getObjects()
        assert len(auditHardwareOnHosts) == 0, u"got: '%s', expected: '%s'" % (
            auditHardwareOnHosts, 0)

        self.backend.auditHardwareOnHost_createObjects(
            self.auditHardwareOnHosts)
        auditHardwareOnHosts = self.backend.auditHardwareOnHost_getObjects()
        assert len(auditHardwareOnHosts) == len(self.auditHardwareOnHosts), u"got: '%s', expected: '%s'" % (
            auditHardwareOnHosts, len(self.auditHardwareOnHosts))

        auditHardwareOnHost4update = self.auditHardwareOnHost4.clone()
        self.backend.auditHardwareOnHost_updateObject(
            auditHardwareOnHost4update)
        auditHardwareOnHosts = self.backend.auditHardwareOnHost_getObjects()
        assert len(auditHardwareOnHosts) == len(self.auditHardwareOnHosts), u"got: '%s', expected: '%s'" % (
            auditHardwareOnHosts, len(self.auditHardwareOnHosts))

        self.backend.auditHardwareOnHost_delete(
            hostId=[], hardwareClass=[], firstseen=[], lastseen=[], state=[])
        auditHardwareOnHosts = self.backend.auditHardwareOnHost_getObjects()
        assert len(auditHardwareOnHosts) == 0, u"got: '%s', expected: '%s'" % (
            auditHardwareOnHosts, 0)

        self.backend.auditHardwareOnHost_createObjects(
            self.auditHardwareOnHosts)
        auditHardwareOnHosts = self.backend.auditHardwareOnHost_getObjects()
        assert len(auditHardwareOnHosts) == len(self.auditHardwareOnHosts), u"got: '%s', expected: '%s'" % (
            auditHardwareOnHosts, len(self.auditHardwareOnHosts))

        self.backend.auditHardwareOnHost_deleteObjects(
            [self.auditHardwareOnHost4, self.auditHardwareOnHost3])
        auditHardwareOnHosts = self.backend.auditHardwareOnHost_getObjects()
        assert len(auditHardwareOnHosts) == len(self.auditHardwareOnHosts) - \
            2, u"got: '%s', expected: '%s'" % (
                auditHardwareOnHosts, len(self.auditHardwareOnHosts) - 2)

        self.backend.auditHardwareOnHost_insertObject(
            self.auditHardwareOnHost4)
        self.backend.auditHardwareOnHost_insertObject(
            self.auditHardwareOnHost3)
        auditHardwareOnHosts = self.backend.auditHardwareOnHost_getObjects()
        assert len(auditHardwareOnHosts) == len(self.auditHardwareOnHosts), u"got: '%s', expected: '%s'" % (
            auditHardwareOnHosts, len(self.auditHardwareOnHosts))

    def testDeletingHostShouldDeleteHardwareAuditData(self):
        """
        Deleting a host should delete it's audit data.
        """
        self.setUpAuditHardwareOnHosts()

        self.backend.host_createObjects(self.client1)
        self.backend.auditHardwareOnHost_createObjects(self.auditHardwareOnHost1)

        self.assertEquals(1, len(self.backend.host_getObjects()),
            'Self-test failed: Too much hosts.')
        self.assertEquals(1, len(self.backend.auditHardwareOnHost_getObjects()),
            'Self-test failed: Too much auditHardwareOnHosts.')

        self.backend.host_deleteObjects([self.client1])

        self.assertEquals(0, len(self.backend.host_getObjects()))
        self.assertEquals(0, len(self.backend.auditHardwareOnHost_getObjects()))

        self.backend.host_createObjects(self.client1)
        self.assertEquals(1, len(self.backend.host_getObjects()))
        self.assertEquals(0, len(self.backend.auditHardwareOnHost_getObjects()))
