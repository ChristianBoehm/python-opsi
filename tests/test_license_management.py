# -*- coding: utf-8 -*-

# This file is part of python-opsi.
# Copyright (C) 2016-2018 uib GmbH <info@uib.de>

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
Testing the license management functionality.

:author: Niko Wenselowski <n.wenselowski@uib.de>
:license: GNU Affero General Public License version 3
"""

from OPSI.Object import (
	LicenseContract, RetailSoftwareLicense, OEMSoftwareLicense,
	VolumeSoftwareLicense, ConcurrentSoftwareLicense, LicensePool,
	SoftwareLicenseToLicensePool, LicenseOnClient)

from .test_hosts import getClients
from .test_products import getProducts


def getLicenseContracts():
	licenseContract1 = LicenseContract(
		id=u'license contract 1',
		description=u'a license contract',
		notes=None,
		partner=u'',
		conclusionDate=None,
		notificationDate=None,
		expirationDate=None
	)

	licenseContract2 = LicenseContract(
		id=u'license contract 2',
		description=u'license contract with company x',
		notes=u'Contract notes',
		partner=u'company x',
		conclusionDate='2009-01-01 00:00:00',
		notificationDate='2010-12-01 00:00:00',
		expirationDate='2011-01-01 00:00:00',
	)

	return licenseContract1, licenseContract2


def testCreatingAndGettingLicenseOnClient(licenseManagementBackend):
	originalLicenseOnClients, _, _, _, _, _, _ = createLicenseOnClients(licenseManagementBackend)

	licenseOnClients = licenseManagementBackend.licenseOnClient_getObjects()
	assert len(licenseOnClients) == len(originalLicenseOnClients)


def createLicenseOnClients(backend):
	(
		softwareLicenseToLicensePools,
		licensePools,
		products,
		softwareLicenses,
		licenseContracts,
		clients
	) = createSoftwareLicenseToLicensePools(backend)

	softwareLicenseToLicensePool1 = softwareLicenseToLicensePools[0]
	client1 = clients[0]
	client2 = clients[1]

	licenseOnClient1 = LicenseOnClient(
		softwareLicenseId=softwareLicenseToLicensePool1.getSoftwareLicenseId(),
		licensePoolId=softwareLicenseToLicensePool1.getLicensePoolId(),
		clientId=client1.getId(),
		licenseKey=softwareLicenseToLicensePool1.getLicenseKey(),
		notes=None
	)

	licenseOnClient2 = LicenseOnClient(
		softwareLicenseId=softwareLicenseToLicensePool1.getSoftwareLicenseId(),
		licensePoolId=softwareLicenseToLicensePool1.getLicensePoolId(),
		clientId=client2.getId(),
		licenseKey=softwareLicenseToLicensePool1.getLicenseKey(),
		notes=u'Installed manually'
	)
	licenseOnClients = [licenseOnClient1, licenseOnClient2]

	backend.licenseOnClient_createObjects(licenseOnClients)

	return (
		licenseOnClients,
		softwareLicenseToLicensePools,
		licensePools,
		products,
		softwareLicenses,
		licenseContracts,
		clients
	)


def testSoftwareLicenseToLicensePoolMethods(licenseManagementBackend):
	originalSoftwareLicenseToLicensePools, _, _, _, _, _ = createSoftwareLicenseToLicensePools(licenseManagementBackend)

	softwareLicenseToLicensePools = licenseManagementBackend.softwareLicenseToLicensePool_getObjects()
	assert len(softwareLicenseToLicensePools) == len(originalSoftwareLicenseToLicensePools)


def createSoftwareLicenseToLicensePools(backend):
	softwareLicenses, licenseContracts, clients = createSoftwareLicenses(backend)

	softwareLicense1 = softwareLicenses[0]
	softwareLicense2 = softwareLicenses[1]
	softwareLicense3 = softwareLicenses[2]
	softwareLicense4 = softwareLicenses[3]

	licensePools, products = createLicensePool(backend)

	licensePool1 = licensePools[0]
	licensePool2 = licensePools[1]

	softwareLicenseToLicensePool1 = SoftwareLicenseToLicensePool(
		softwareLicenseId=softwareLicense1.getId(),
		licensePoolId=licensePool1.getId(),
		licenseKey='xxxxx-yyyyy-zzzzz-aaaaa-bbbbb'
	)

	softwareLicenseToLicensePool2 = SoftwareLicenseToLicensePool(
		softwareLicenseId=softwareLicense2.getId(),
		licensePoolId=licensePool1.getId(),
		licenseKey=''
	)

	softwareLicenseToLicensePool3 = SoftwareLicenseToLicensePool(
		softwareLicenseId=softwareLicense3.getId(),
		licensePoolId=licensePool2.getId(),
		licenseKey='12345-56789-00000-11111-aaaaa'
	)

	softwareLicenseToLicensePool4 = SoftwareLicenseToLicensePool(
		softwareLicenseId=softwareLicense4.getId(),
		licensePoolId=licensePool2.getId(),
		licenseKey=None
	)

	softwareLicenseToLicensePools = [
		softwareLicenseToLicensePool1, softwareLicenseToLicensePool2,
		softwareLicenseToLicensePool3, softwareLicenseToLicensePool4
	]

	backend.softwareLicenseToLicensePool_createObjects(softwareLicenseToLicensePools)

	return (
		softwareLicenseToLicensePools,
		licensePools,
		products,
		softwareLicenses,
		licenseContracts,
		clients
	)


def testSoftwareLicenseMethods(licenseManagementBackend):
	licenses, _, _ = createSoftwareLicenses(licenseManagementBackend)

	softwareLicenses = licenseManagementBackend.softwareLicense_getObjects()
	assert len(softwareLicenses) == len(licenses)


def createSoftwareLicenses(backend):
	licenseContracts = createLicenseContracts(backend)

	licenseContract1 = licenseContracts[0]
	licenseContract2 = licenseContracts[1]

	clients = getClients()
	for client in clients:
		client.setDefaults()
	backend.host_createObjects(clients)

	client1 = clients[0]

	softwareLicense1 = RetailSoftwareLicense(
		id=u'software license 1',
		licenseContractId=licenseContract1.getId(),
		maxInstallations=2,
		boundToHost=None,
		expirationDate=licenseContract1.getExpirationDate()
	)

	softwareLicense2 = OEMSoftwareLicense(
		id=u'software license 2',
		licenseContractId=licenseContract1.getId(),
		maxInstallations=None,
		boundToHost=client1.getId(),
		expirationDate=licenseContract1.getExpirationDate()
	)

	softwareLicense3 = VolumeSoftwareLicense(
		id=u'software license 3',
		licenseContractId=licenseContract2.getId(),
		maxInstallations=100,
		boundToHost=None,
		expirationDate=licenseContract2.getExpirationDate()
	)

	softwareLicense4 = ConcurrentSoftwareLicense(
		id=u'software license 4',
		licenseContractId=licenseContract2.getId(),
		maxInstallations=10,
		boundToHost=None,
		expirationDate=licenseContract2.getExpirationDate()
	)

	softwareLicenses = (softwareLicense1, softwareLicense2, softwareLicense3, softwareLicense4)
	backend.softwareLicense_createObjects(softwareLicenses)

	return (
		softwareLicenses,
		licenseContracts,
		clients
	)


def testLicenseContractMethods(licenseManagementBackend):
	originalLicenseContracts = createLicenseContracts(licenseManagementBackend)

	licenseContracts = licenseManagementBackend.licenseContract_getObjects()
	assert len(licenseContracts) == len(originalLicenseContracts)


def createLicenseContracts(backend):
	licenseContracts = getLicenseContracts()

	backend.licenseContract_createObjects(licenseContracts)

	return licenseContracts


def testSelectingInvalidLicensePoolById(licenseManagementBackend):
	originalLicensePools, _ = createLicensePool(licenseManagementBackend)

	licensePool1 = originalLicensePools[0]
	licensePool2 = originalLicensePools[1]

	licensePoolsFromBackend = licenseManagementBackend.licensePool_getObjects(
		id=licensePool2.id,
		productIds=licensePool1.productIds
	)
	assert 0 == len(licensePoolsFromBackend)


def testCheckingProductIdsInLicensePool(licenseManagementBackend):
	originalLicensePools, _ = createLicensePool(licenseManagementBackend)

	licensePools = licenseManagementBackend.licensePool_getObjects()
	assert len(licensePools) == len(originalLicensePools)

	for licensePool in licensePools:
		assert any(
			set(licensePool.getProductIds()) == set(origLicensePool.getProductIds())
			for origLicensePool in originalLicensePools
			if licensePool.getId() == origLicensePool.getId()
		)


def testSelectingLicensePoolWithoutProducts(licenseManagementBackend):
	originalLicensePools, _ = createLicensePool(licenseManagementBackend)

	licensePools = licenseManagementBackend.licensePool_getObjects(productIds=None)
	assert len(originalLicensePools) == len(licensePools)


def testSelectLicensePoolByInvalidProductReturnsNoPools(licenseManagementBackend):
	originalLicensePools, _ = createLicensePool(licenseManagementBackend)

	assert len(licenseManagementBackend.licensePool_getObjects()) > 0

	licensePools = licenseManagementBackend.licensePool_getObjects(productIds=['xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx'])
	assert 0 == len(licensePools), u"Did not expect any license pools, but found %s on backend." % len(licensePools)


def testSelectingLicensePoolsByProductIds(licenseManagementBackend):
	originalLicensePools, _ = createLicensePool(licenseManagementBackend)

	licensePool1 = originalLicensePools[0]
	assert licensePool1.productIds

	licensePools = licenseManagementBackend.licensePool_getObjects(productIds=licensePool1.productIds)
	assert 1 == len(licensePools)
	assert licensePools[0].getId() == licensePool1.getId()


def createLicensePool(backend):
	products = getProducts()
	backend.product_createObjects(products)

	product1 = products[0]
	product2 = products[1]

	licensePool1 = LicensePool(
		id=u'license_pool_1',
		description=u'licenses for product1',
		productIds=product1.getId()
	)

	licensePool2 = LicensePool(
		id=u'license_pool_2',
		description=u'licenses for product2',
		productIds=product2.getId()
	)

	backend.licensePool_createObjects((licensePool1, licensePool2))

	return (
		(licensePool1, licensePool2),
		products
	)
