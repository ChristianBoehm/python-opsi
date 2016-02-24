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
Tests for the dynamically loaded legacy extensions.

This tests what usually is found under
``/etc/opsi/backendManager/extend.de/20_legacy.conf``.

The legacy extensions are to maintain backwards compatibility for scripts
that were written for opsi 3.

:author: Niko Wenselowski <n.wenselowski@uib.de>
:license: GNU Affero General Public License version 3
"""

from __future__ import absolute_import

from OPSI.Object import (OpsiClient, LocalbootProduct, ProductOnClient,
                         OpsiDepotserver, ProductOnDepot, UnicodeConfig,
                         ConfigState)
from OPSI.Types import BackendMissingDataError
from .Backends.File import FileBackendBackendManagerMixin
from .helpers import unittest


class LegacyFunctionsTestCase(unittest.TestCase, FileBackendBackendManagerMixin):
    "Testing the legacy / simple functins."

    def setUp(self):
        self.setUpBackend()

    def tearDown(self):
        self.tearDownBackend()

    def testGetGeneralConfigValueFailsWithInvalidObjectId(self):
        self.assertRaises(ValueError, self.backend.getGeneralConfig_hash, 'foo')

    def testGetGeneralConfig(self):
        """
        Calling the function with some valid FQDN must not fail.
        """
        self.backend.getGeneralConfig_hash('some.client.fqdn')

    def testSetGeneralConfigValue(self):
        # required by File-backend
        self.backend.host_createOpsiClient('some.client.fqdn')

        self.backend.setGeneralConfigValue('foo', 'bar', 'some.client.fqdn')

        self.assertEquals(
            'bar',
            self.backend.getGeneralConfigValue('foo', 'some.client.fqdn')
        )

    def testGetDomainShouldWork(self):
        self.assertNotEqual('', self.backend.getDomain())

    def testSetActionRequestWhereOutdated(self):
        self.assertRaises(TypeError, self.backend.setActionRequestWhereOutdated)
        self.assertRaises(TypeError, self.backend.setActionRequestWhereOutdated, 'setup')

        self.assertRaises(BackendMissingDataError, self.backend.setActionRequestWhereOutdated, 'setup', 'unknownProductId')

        client_with_old_product = OpsiClient(id='clientwithold.test.invalid')
        client_with_current_product = OpsiClient(id='clientwithcurrent.test.invalid')
        client_without_product = OpsiClient(id='clientwithout.test.invalid')
        client_unknown_status = OpsiClient(id='clientunkown.test.invalid')
        clients = [client_with_old_product, client_with_current_product,
                   client_without_product, client_unknown_status]

        depot = OpsiDepotserver(id='depotserver1.test.invalid')

        self.backend.host_createObjects([depot, client_with_old_product,
                                        client_with_current_product,
                                        client_without_product,
                                        client_unknown_status])

        old_product = LocalbootProduct('thunderheart', '1', '1')
        new_product = LocalbootProduct('thunderheart', '1', '2')

        self.backend.product_createObjects([old_product, new_product])

        poc = ProductOnClient(
            clientId=client_with_old_product.id,
            productId=old_product.id,
            productType=old_product.getType(),
            productVersion=old_product.productVersion,
            packageVersion=old_product.packageVersion,
            installationStatus='installed',
            actionResult='successful'
        )
        poc2 = ProductOnClient(
            clientId=client_with_current_product.id,
            productId=new_product.id,
            productType=new_product.getType(),
            productVersion=new_product.productVersion,
            packageVersion=new_product.packageVersion,
            installationStatus='installed',
            actionResult='successful'
        )
        poc3 = ProductOnClient(
            clientId=client_unknown_status.id,
            productId=old_product.id,
            productType=old_product.getType(),
            productVersion=old_product.productVersion,
            packageVersion=old_product.packageVersion,
            installationStatus='unknown',
        )

        self.backend.productOnClient_createObjects([poc, poc2, poc3])

        installedProductOnDepot = ProductOnDepot(
            productId=new_product.id,
            productType=new_product.getType(),
            productVersion=new_product.productVersion,
            packageVersion=new_product.packageVersion,
            depotId=depot.getId(),
            locked=False
        )

        self.backend.productOnDepot_createObjects([installedProductOnDepot])

        clientConfigDepotId = UnicodeConfig(
            id=u'clientconfig.depot.id',
            description=u'Depotserver to use',
            possibleValues=[],
            defaultValues=[depot.id]
        )

        self.backend.config_createObjects(clientConfigDepotId)

        for client in clients:
            clientDepotMappingConfigState = ConfigState(
                configId=u'clientconfig.depot.id',
                objectId=client.getId(),
                values=depot.getId()
            )

            self.backend.configState_createObjects(clientDepotMappingConfigState)

        # Starting the checks
        self.assertFalse(self.backend.productOnClient_getObjects(productId=new_product.id, clientId=client_without_product.id))
        self.assertFalse(self.backend.productOnClient_getObjects(productId=new_product.id, clientId=client_with_old_product.id, actionRequest="setup"))
        self.assertTrue(self.backend.productOnClient_getObjects(productId=new_product.id, clientId=client_with_current_product.id))
        self.assertTrue(self.backend.productOnClient_getObjects(productId=old_product.id, clientId=client_unknown_status.id, installationStatus='unknown'))

        clientIDs = self.backend.setActionRequestWhereOutdated('setup', new_product.id)

        self.assertEquals(1, len(clientIDs))
        self.assertTrue(client_with_old_product.id, list(clientIDs)[0])
        self.assertFalse(self.backend.productOnClient_getObjects(productId=new_product.id, clientId=client_without_product.id))
        poc = self.backend.productOnClient_getObjects(productId=new_product.id, clientId=client_with_old_product.id)[0]
        self.assertEquals("setup", poc.actionRequest)
        poc = self.backend.productOnClient_getObjects(productId=new_product.id, clientId=client_with_current_product.id)[0]
        self.assertNotEquals("setup", poc.actionRequest)
        poc = self.backend.productOnClient_getObjects(productId=old_product.id, clientId=client_unknown_status.id)[0]
        self.assertNotEquals("setup", poc.actionRequest)
        self.assertEquals("unknown", poc.installationStatus)

    def testUninstallWhereInstalled(self):
        self.assertRaises(TypeError, self.backend.uninstallWhereInstalled)

        self.assertRaises(BackendMissingDataError, self.backend.uninstallWhereInstalled, 'unknownProductId')

        client_with_product = OpsiClient(id='clientwith.test.invalid')
        client_without_product = OpsiClient(id='clientwithout.test.invalid')
        depot = OpsiDepotserver(id='depotserver1.test.invalid')

        self.backend.host_createObjects([depot, client_with_product,
                                         client_without_product])

        product = LocalbootProduct('thunderheart', '1', '1', uninstallScript='foo.bar')
        productWithoutScript = LocalbootProduct('installOnly', '1', '1')

        self.backend.product_createObjects([product, productWithoutScript])

        installedProductOnDepot = ProductOnDepot(
            productId=product.id,
            productType=product.getType(),
            productVersion=product.productVersion,
            packageVersion=product.packageVersion,
            depotId=depot.id,
            locked=False
        )
        installedProductOnDepot2 = ProductOnDepot(
            productId=productWithoutScript.id,
            productType=productWithoutScript.getType(),
            productVersion=productWithoutScript.productVersion,
            packageVersion=productWithoutScript.packageVersion,
            depotId=depot.id,
            locked=False
        )

        self.backend.productOnDepot_createObjects([installedProductOnDepot,
                                                   installedProductOnDepot2])

        self.assertFalse(self.backend.uninstallWhereInstalled('thunderheart'))

        poc = ProductOnClient(
            clientId=client_with_product.id,
            productId=product.id,
            productType=product.getType(),
            productVersion=product.productVersion,
            packageVersion=product.packageVersion,
            installationStatus='installed',
            actionResult='successful'
        )
        pocWithoutScript = ProductOnClient(
            clientId=client_with_product.id,
            productId=productWithoutScript.id,
            productType=productWithoutScript.getType(),
            productVersion=productWithoutScript.productVersion,
            packageVersion=productWithoutScript.packageVersion,
            installationStatus='installed',
            actionResult='successful'
        )
        self.backend.productOnClient_createObjects([poc, pocWithoutScript])

        clientConfigDepotId = UnicodeConfig(
            id=u'clientconfig.depot.id',
            description=u'Depotserver to use',
            possibleValues=[],
            defaultValues=[depot.id]
        )

        self.backend.config_createObjects(clientConfigDepotId)

        for client in (client_with_product, client_without_product):
            clientDepotMappingConfigState = ConfigState(
                configId=u'clientconfig.depot.id',
                objectId=client.getId(),
                values=depot.getId()
            )

            self.backend.configState_createObjects(clientDepotMappingConfigState)

        clientIDs = self.backend.uninstallWhereInstalled(product.id)

        self.assertEquals(1, len(clientIDs))
        pocAfter = self.backend.productOnClient_getObjects(productId=product.id, clientId=client_with_product.id)
        self.assertEquals(1, len(pocAfter))
        pocAfter = pocAfter[0]
        self.assertEquals("uninstall", pocAfter.actionRequest)

        clientIDs = self.backend.uninstallWhereInstalled(productWithoutScript.id)
        self.assertEquals(0, len(clientIDs))


    def testUpdateWhereInstalled(self):
        self.assertRaises(BackendMissingDataError, self.backend.updateWhereInstalled, 'unknown')

        self.assertRaises(BackendMissingDataError, self.backend.updateWhereInstalled, 'unknown')

        client_with_old_product = OpsiClient(id='clientwithold.test.invalid')
        client_with_current_product = OpsiClient(id='clientwithcurrent.test.invalid')
        client_without_product = OpsiClient(id='clientwithout.test.invalid')

        depot = OpsiDepotserver(id='depotserver1.test.invalid')

        self.backend.host_createObjects([depot, client_with_old_product,
                                        client_with_current_product,
                                        client_without_product])

        old_product = LocalbootProduct('thunderheart', '1', '1')
        new_product = LocalbootProduct('thunderheart', '1', '2',
                                       updateScript='foo.opsiscript')

        self.backend.product_createObjects([old_product, new_product])

        self.assertFalse(self.backend.updateWhereInstalled('thunderheart'))

        poc = ProductOnClient(
            clientId=client_with_old_product.id,
            productId=old_product.id,
            productType=old_product.getType(),
            productVersion=old_product.productVersion,
            packageVersion=old_product.packageVersion,
            installationStatus='installed',
            actionResult='successful'
        )
        poc2 = ProductOnClient(
            clientId=client_with_current_product.id,
            productId=new_product.id,
            productType=new_product.getType(),
            productVersion=new_product.productVersion,
            packageVersion=new_product.packageVersion,
            installationStatus='installed',
            actionResult='successful'
        )

        self.backend.productOnClient_createObjects([poc, poc2])

        installedProductOnDepot = ProductOnDepot(
            productId=new_product.id,
            productType=new_product.getType(),
            productVersion=new_product.productVersion,
            packageVersion=new_product.packageVersion,
            depotId=depot.getId(),
            locked=False
        )

        self.backend.productOnDepot_createObjects([installedProductOnDepot])

        clientConfigDepotId = UnicodeConfig(
            id=u'clientconfig.depot.id',
            description=u'Depotserver to use',
            possibleValues=[],
            defaultValues=[depot.id]
        )

        self.backend.config_createObjects(clientConfigDepotId)

        for client in (client_with_current_product, client_with_old_product, client_without_product):
            clientDepotMappingConfigState = ConfigState(
                configId=u'clientconfig.depot.id',
                objectId=client.getId(),
                values=depot.getId()
            )

            self.backend.configState_createObjects(clientDepotMappingConfigState)

        # Starting the checks
        self.assertFalse(self.backend.productOnClient_getObjects(productId=new_product.id, clientId=client_without_product.id))
        self.assertFalse(self.backend.productOnClient_getObjects(productId=new_product.id, clientId=client_with_old_product.id, actionRequest="setup"))
        self.assertTrue(self.backend.productOnClient_getObjects(productId=new_product.id, clientId=client_with_current_product.id))

        clientIDs = self.backend.updateWhereInstalled('thunderheart')

        self.assertFalse(self.backend.productOnClient_getObjects(productId=new_product.id, clientId=client_without_product.id))
        poc = self.backend.productOnClient_getObjects(productId=new_product.id, clientId=client_with_old_product.id)[0]
        self.assertEquals("update", poc.actionRequest)
        poc = self.backend.productOnClient_getObjects(productId=new_product.id, clientId=client_with_current_product.id)[0]
        self.assertEquals("update", poc.actionRequest)

        self.assertEquals(2, len(clientIDs))
        self.assertTrue(client_with_old_product.id in clientIDs)
        self.assertTrue(client_with_current_product.id in clientIDs)

    def testSetupWhereNotInstalled(self):
        self.assertRaises(TypeError, self.backend.setupWhereNotInstalled)

        self.assertRaises(BackendMissingDataError, self.backend.setupWhereNotInstalled, 'unknownProductId')

        client_with_current_product = OpsiClient(id='clientwithcurrent.test.invalid')
        client_without_product = OpsiClient(id='clientwithout.test.invalid')

        depot = OpsiDepotserver(id='depotserver1.test.invalid')

        self.backend.host_createObjects([depot,
                                        client_with_current_product,
                                        client_without_product])

        product = LocalbootProduct('thunderheart', '1', '1', setupScript='foo.bar')

        self.backend.product_createObjects([product])

        poc = ProductOnClient(
            clientId=client_with_current_product.id,
            productId=product.id,
            productType=product.getType(),
            productVersion=product.productVersion,
            packageVersion=product.packageVersion,
            installationStatus='installed',
            actionResult='successful'
        )

        self.backend.productOnClient_createObjects([poc])

        installedProductOnDepot = ProductOnDepot(
            productId=product.id,
            productType=product.getType(),
            productVersion=product.productVersion,
            packageVersion=product.packageVersion,
            depotId=depot.getId(),
            locked=False
        )

        self.backend.productOnDepot_createObjects([installedProductOnDepot])

        clientConfigDepotId = UnicodeConfig(
            id=u'clientconfig.depot.id',
            description=u'Depotserver to use',
            possibleValues=[],
            defaultValues=[depot.id]
        )

        self.backend.config_createObjects(clientConfigDepotId)

        for client in (client_with_current_product, client_without_product):
            clientDepotMappingConfigState = ConfigState(
                configId=u'clientconfig.depot.id',
                objectId=client.getId(),
                values=depot.getId()
            )

            self.backend.configState_createObjects(clientDepotMappingConfigState)

        # Starting the checks
        self.assertFalse(self.backend.productOnClient_getObjects(productId=product.id, clientId=client_without_product.id))
        self.assertTrue(self.backend.productOnClient_getObjects(productId=product.id, clientId=client_with_current_product.id))

        clientIDs = self.backend.setupWhereNotInstalled(product.id)

        self.assertEquals(1, len(clientIDs))
        poc = self.backend.productOnClient_getObjects(productId=product.id, clientId=client_without_product.id)[0]
        self.assertEquals("setup", poc.actionRequest)


class LegacyConfigStateAccessTestCase(unittest.TestCase, FileBackendBackendManagerMixin):
    """
    Testing legacy access to ConfigStates.
    """

    def setUp(self):
        self.setUpBackend()

    def tearDown(self):
        self.tearDownBackend()

    def testNoConfigReturnsNoValue(self):
        self.assertEquals(None, self.backend.getGeneralConfigValue(None))
        self.assertEquals(None, self.backend.getGeneralConfigValue(""))

    def testEmptyAfterStart(self):
        self.assertEquals({}, self.backend.getGeneralConfig_hash())

    def testUnabledToHandleNonTextValues(self):
        function = self.backend.setGeneralConfig
        self.assertRaises(Exception, function, {"test": True})
        self.assertRaises(Exception, function, {"test": 1})
        self.assertRaises(Exception, function, {"test": None})

    def testSetGeneralConfigValue(self):
        config = {"test.truth": "True", "test.int": "2"}
        self.backend.setGeneralConfig(config)

        for key, value in config.items():
            self.assertEquals(value, self.backend.getGeneralConfigValue(key))

        self.assertNotEquals({}, self.backend.getGeneralConfig_hash())
        self.assertEquals(2, len(self.backend.getGeneralConfig_hash()))

    def testSetGeneralConfigValueTypeConversion(self):
        trueValues = set(['yes', 'on', '1', 'true'])
        falseValues = set(['no', 'off', '0', 'false'])

        for value in trueValues:
            self.backend.setGeneralConfig({"bool": value})
            self.assertEquals("True", self.backend.getGeneralConfigValue("bool"))

        for value in falseValues:
            self.backend.setGeneralConfig({"bool": value})
            self.assertEquals("False", self.backend.getGeneralConfigValue("bool"))

        self.backend.setGeneralConfig({"bool": "noconversion"})
        self.assertEquals("noconversion", self.backend.getGeneralConfigValue("bool"))

    def testRemovingMissingValue(self):
        config = {"test.truth": "True", "test.int": "2"}
        self.backend.setGeneralConfig(config)
        self.assertEquals(2, len(self.backend.getGeneralConfig_hash()))

        del config["test.int"]
        self.backend.setGeneralConfig(config)
        self.assertEquals(1, len(self.backend.getGeneralConfig_hash()))

    def testMassFilling(self):
        numberOfConfigs = 50  # len(config) will be double

        config = {}
        for value in range(numberOfConfigs):
            config["bool.{0}".format(value)] = str(value % 2 == 0)

        for value in range(numberOfConfigs):
            config["normal.{0}".format(value)] = "norm-{0}".format(value)

        self.assertEquals(numberOfConfigs * 2, len(config))

        self.backend.setGeneralConfig(config)

        configFromBackend = self.backend.getGeneralConfig_hash()
        self.assertEquals(config, configFromBackend)


if __name__ == '__main__':
    unittest.main()
