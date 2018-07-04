# -*- coding: utf-8 -*-

# This file is part of python-opsi.
# Copyright (C) 2013-2018 uib GmbH <info@uib.de>

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
Testing the functionality of working with hosts.

:author: Niko Wenselowski <n.wenselowski@uib.de>
:license: GNU Affero General Public License version 3
"""

from __future__ import absolute_import

import itertools
import socket

import pytest

from OPSI.Exceptions import BackendError, BackendMissingDataError
from OPSI.Object import (HostGroup, ObjectToGroup, OpsiClient, OpsiConfigserver,
    OpsiDepotserver)
from OPSI.Util import randomString


def getLocalHostFqdn():
    fqdn = socket.getfqdn()
    if fqdn.count('.') < 2:
        raise RuntimeError(u"Failed to get fqdn: %s" % fqdn)

    return fqdn


def getClients():
    client1 = OpsiClient(
        id='client1.test.invalid',
        description='Test client 1',
        notes='Notes ...',
        hardwareAddress='00:01:02:03:04:05',
        ipAddress='192.168.1.100',
        lastSeen='2009-01-01 00:00:00',
        opsiHostKey='45656789789012789012345612340123',
        inventoryNumber=None
    )

    client2 = OpsiClient(
        id='client2.test.invalid',
        description='Test client 2',
        notes=';;;;;;;;;;;;;;',
        hardwareAddress='00-ff0aa3:0b-B5',
        opsiHostKey='59051234345678890121678901223467',
        inventoryNumber='00000000003',
        oneTimePassword='logmein'
    )

    client3 = OpsiClient(
        id='client3.test.invalid',
        description='Test client 3',
        notes='#############',
        inventoryNumber='XYZABC_1200292'
    )

    client4 = OpsiClient(
        id='client4.test.invalid',
        description='Test client 4',
    )

    client5 = OpsiClient(
        id='client5.test.invalid',
        description='Test client 5',
        oneTimePassword='abe8327kjdsfda'
    )

    client6 = OpsiClient(
        id='client6.test.invalid',
        description='Test client 6',
    )

    client7 = OpsiClient(
        id='client7.test.invalid',
        description='Test client 7',
    )

    return client1, client2, client3, client4, client5, client6, client7


def getConfigServer():
    serverId = getLocalHostFqdn()

    return OpsiConfigserver(
        id=serverId,
        opsiHostKey='71234545689056789012123678901234',
        depotLocalUrl='file:///var/lib/opsi/depot',
        depotRemoteUrl=u'smb://%s/opsi_depot' % serverId.split('.')[0],
        repositoryLocalUrl='file:///var/lib/opsi/repository',
        repositoryRemoteUrl=u'webdavs://%s:4447/repository' % serverId,
        workbenchLocalUrl='file:///var/lib/opsi/workbench',
        workbenchRemoteUrl=u'smb://%s/opsi_workbench' % serverId.split('.')[0],
        description='The configserver',
        notes='Config 1',
        hardwareAddress=None,
        ipAddress=None,
        inventoryNumber='00000000001',
        networkAddress='192.168.1.0/24',
        maxBandwidth=10000
    )


def getDepotServers():
    depotserver1 = OpsiDepotserver(
        id='depotserver1.uib.local',
        opsiHostKey='19012334567845645678901232789012',
        depotLocalUrl='file:///var/lib/opsi/depot',
        depotRemoteUrl='smb://depotserver1.test.invalid/opsi_depot',
        depotWebdavUrl=u'webdavs://depotserver1.test.invalid:4447/depot',
        repositoryLocalUrl='file:///var/lib/opsi/repository',
        repositoryRemoteUrl='webdavs://depotserver1.test.invalid:4447/repository',
        workbenchLocalUrl='file:///var/lib/opsi/workbench',
        workbenchRemoteUrl=u'smb://depotserver1.test.invalid/opsi_workbench',
        description='A depot',
        notes='D€pot 1',
        hardwareAddress=None,
        ipAddress=None,
        inventoryNumber='00000000002',
        networkAddress='192.168.2.0/24',
        maxBandwidth=10000
    )

    depotserver2 = OpsiDepotserver(
        id='depotserver2.test.invalid',
        opsiHostKey='93aa22f38a678c64ef678a012d2e82f2',
        depotLocalUrl='file:///var/lib/opsi/depot',
        depotRemoteUrl='smb://depotserver2.test.invalid/opsi_depot',
        repositoryLocalUrl='file:///var/lib/opsi/repository',
        repositoryRemoteUrl='webdavs://depotserver2.test.invalid:4447/repository',
        workbenchLocalUrl='file:///var/lib/opsi/workbench',
        workbenchRemoteUrl=u'smb://depotserver2.test.invalid/opsi_workbench',
        description='Second depot',
        notes=None,  # no notes here
        hardwareAddress='00:01:09:07:11:aa',
        ipAddress='192.168.10.1',
        inventoryNumber='',
        networkAddress='192.168.10.0/24',
        maxBandwidth=240000
    )

    return depotserver1, depotserver2


def test_getHostsHostOnBackend(extendedConfigDataBackend):
    clients = getClients()
    configServer = getConfigServer()
    depots = getDepotServers()

    hostsOriginal = list(clients) + [configServer] + list(depots)
    extendedConfigDataBackend.host_createObjects(hostsOriginal)

    hosts = extendedConfigDataBackend.host_getObjects()
    assert hosts
    assert len(hosts) == len(hostsOriginal)


def test_verifyHosts(extendedConfigDataBackend):

    def nullifyUncomparableValues(hostDict):
        keys = (
            'lastSeen', 'created', 'inventoryNumber', 'notes', 'opsiHostKey',
            'isMasterDepot'
        )
        for key in keys:
            hostDict[key] = None

    clients = getClients()
    hostsOriginal = {client.id: client for client in clients}
    configServer = getConfigServer()
    hostsOriginal.update({configServer.id: configServer})
    depots = getDepotServers()
    hostsOriginal.update({depot.id: depot for depot in depots})
    extendedConfigDataBackend.host_createObjects(list(hostsOriginal.values()))

    hosts = extendedConfigDataBackend.host_getObjects()
    assert hosts
    for host in hosts:
        assert host.getOpsiHostKey() is not None

        h = hostsOriginal[host.id]
        h1 = h.toHash()
        h2 = host.toHash()
        nullifyUncomparableValues(h1)
        nullifyUncomparableValues(h2)

        assert h1 == h2


def test_createDepotserverOnBackend(extendedConfigDataBackend):
    clients = getClients()
    configServer = getConfigServer()
    depots = getDepotServers()
    hostsOriginal = list(clients) + [configServer] + list(depots)
    extendedConfigDataBackend.host_createObjects(hostsOriginal)

    hosts = extendedConfigDataBackend.host_getObjects(type='OpsiConfigserver')
    assert len(hosts) == 1


def test_clientsOnBackend(extendedConfigDataBackend):
    clients = getClients()
    configServer = getConfigServer()
    depots = getDepotServers()
    hostsOriginal = list(clients) + [configServer] + list(depots)
    extendedConfigDataBackend.host_createObjects(hostsOriginal)

    hosts = extendedConfigDataBackend.host_getObjects(type=[clients[0].getType()])
    assert len(hosts) == len(clients)
    ids = [host.getId() for host in hosts]

    for client in clients:
        assert client.getId() in ids


def test_selectClientsOnBackend(extendedConfigDataBackend):
    clients = getClients()
    extendedConfigDataBackend.host_createObjects(clients)

    client1, client2 = clients[:2]

    hosts = extendedConfigDataBackend.host_getObjects(id=[client1.getId(), client2.getId()])
    assert len(hosts) == 2

    ids = [host.getId() for host in hosts]
    assert client1.getId() in ids
    assert client2.getId() in ids


def test_hostAttributes(extendedConfigDataBackend):
    clients = getClients()
    configServer = getConfigServer()
    depots = getDepotServers()
    hostsOriginal = list(clients) + [configServer] + list(depots)
    extendedConfigDataBackend.host_createObjects(hostsOriginal)

    hosts = extendedConfigDataBackend.host_getObjects(attributes=['description', 'notes'], ipAddress=[None])
    count = sum(1 for host in hostsOriginal if host.getIpAddress() is None)

    assert len(hosts) == count
    for host in hosts:
        assert host.getIpAddress() is None
        assert host.getInventoryNumber() is None
        assert host.getNotes() is not None
        assert host.getDescription() is not None

    hosts = extendedConfigDataBackend.host_getObjects(attributes=['description', 'notes'], ipAddress=None)
    assert len(hosts) == len(hostsOriginal)

    for host in hosts:
        assert host.getIpAddress() is None
        assert host.getInventoryNumber() is None


def test_selectClientsByDescription(extendedConfigDataBackend):
    clients = getClients()
    configServer = getConfigServer()
    depots = getDepotServers()
    hostsOriginal = list(clients) + [configServer] + list(depots)
    extendedConfigDataBackend.host_createObjects(hostsOriginal)

    client2 = clients[1]

    hosts = extendedConfigDataBackend.host_getObjects(type=["OpsiClient"], description=client2.getDescription())

    assert len(hosts) == 1
    assert hosts[0].id == client2.getId()
    assert hosts[0].description == client2.getDescription()


def test_selectClientById(extendedConfigDataBackend):
    clients = getClients()
    extendedConfigDataBackend.host_createObjects(clients)
    client1 = clients[0]

    hosts = extendedConfigDataBackend.host_getObjects(attributes=['id', 'description'], id=client1.getId())

    assert len(hosts) == 1
    assert hosts[0].id == client1.getId()
    assert hosts[0].description == client1.getDescription()


def test_deleteClientFromBackend(extendedConfigDataBackend):
    clients = list(getClients())
    configServer = getConfigServer()
    depots = getDepotServers()
    hostsOriginal = list(clients) + [configServer] + list(depots)
    extendedConfigDataBackend.host_createObjects(hostsOriginal)

    client2 = clients[1]
    extendedConfigDataBackend.host_deleteObjects(client2)

    hosts = extendedConfigDataBackend.host_getObjects(type=["OpsiClient"])
    assert len(hosts) == len(clients) - 1

    ids = [host.getId() for host in hosts]
    assert client2.getId() not in ids

    del clients[clients.index(client2)]
    for client in clients:
        assert client.getId() in ids


def test_updateObjectOnBackend(extendedConfigDataBackend):
    clients = getClients()
    extendedConfigDataBackend.host_createObjects(clients)

    client2 = clients[1]
    client2.setDescription('Updated')
    extendedConfigDataBackend.host_updateObject(client2)
    hosts = extendedConfigDataBackend.host_getObjects(description='Updated')
    assert len(hosts) == 1
    assert hosts[0].getId() == client2.getId()


def test_createObjectOnBackend(extendedConfigDataBackend):
    clients = getClients()
    extendedConfigDataBackend.host_createObjects(clients)

    client2 = clients[1]
    extendedConfigDataBackend.host_deleteObjects(client2)

    client2.setDescription(u'Test client 2')
    extendedConfigDataBackend.host_createObjects(client2)
    hosts = extendedConfigDataBackend.host_getObjects(attributes=['id', 'description'], id=client2.getId())
    assert len(hosts) == 1
    assert hosts[0].getId() == client2.getId()
    assert hosts[0].getDescription() == u'Test client 2'


def testDeletingAllHosts(extendedConfigDataBackend):
    extendedConfigDataBackend.host_createObjects(getClients())

    hosts = extendedConfigDataBackend.host_getObjects()
    assert len(hosts) > 1
    extendedConfigDataBackend.host_delete(id=[])  # Deletes all clients
    hosts = extendedConfigDataBackend.host_getObjects()

    # This is special for the file backend: there the ConfigServer
    # will stay in the backend and does not get deleted.
    assert len(hosts) <= 1


def testHost_GetIdents(extendedConfigDataBackend):
    configserver1 = getConfigServer()
    depots = getDepotServers()
    clients = getClients()

    extendedConfigDataBackend.host_createObjects(configserver1)
    extendedConfigDataBackend.host_createObjects(depots)
    extendedConfigDataBackend.host_createObjects(clients)
    extendedConfigDataBackend.host_createOpsiClient(id='client100.test.invalid')
    extendedConfigDataBackend.host_createOpsiDepotserver(id='depot100.test.invalid')

    knownIdents = [host.getIdent(returnType='dict') for host in itertools.chain(clients, depots, [configserver1])]
    knownIdents.append({'id': 'depot100.test.invalid'})
    knownIdents.append({'id': 'client100.test.invalid'})
    knownIdents = set(selfIdent['id'] for selfIdent in knownIdents)

    ids = extendedConfigDataBackend.host_getIdents()
    assert len(ids) == len(knownIdents)
    for ident in ids:
        assert ident in knownIdents

    ids = extendedConfigDataBackend.host_getIdents(returnType='tuple')
    assert len(ids) == len(knownIdents)
    for ident in ids:
        assert ident[0] in knownIdents

    ids = extendedConfigDataBackend.host_getIdents(returnType='list')
    assert len(ids) == len(knownIdents)
    for ident in ids:
        assert ident[0] in knownIdents

    ids = extendedConfigDataBackend.host_getIdents(returnType='dict')
    assert len(ids) == len(knownIdents)
    for ident in ids:
        assert ident['id'] in knownIdents


def testRenamingOpsiClientFailsIfNewIdAlreadyExisting(extendedConfigDataBackend):
    backend = extendedConfigDataBackend

    host = OpsiClient(id='old.test.invalid')
    anotherHost = OpsiClient(id='new.test.invalid')

    backend.host_insertObject(host)
    backend.host_insertObject(anotherHost)

    with pytest.raises(BackendError):
        backend.host_renameOpsiClient(host.id, anotherHost.id)


def testRenamingOpsiClientFailsIfOldClientMissing(extendedConfigDataBackend):
    with pytest.raises(BackendMissingDataError):
        extendedConfigDataBackend.host_renameOpsiClient('nonexisting.test.invalid', 'new.test.invalid')


def testRenamingOpsiClient(extendedConfigDataBackend):
    backend = extendedConfigDataBackend

    host = OpsiClient(id='jacket.test.invalid')
    backend.host_insertObject(host)

    protagonists = HostGroup("protagonists")
    backend.group_insertObject(protagonists)

    backend.objectToGroup_insertObject(ObjectToGroup(protagonists.getType(), protagonists.id, host.id))

    oldId = host.id
    newId = 'richard.test.invalid'

    backend.host_renameOpsiClient(oldId, newId)

    assert not backend.host_getObjects(id=oldId)
    assert backend.host_getObjects(id=newId)

    # We want to make sure that the membership of groups does get
    # changed aswell.
    assert not backend.objectToGroup_getObjects(objectId=oldId)
    memberships = backend.objectToGroup_getObjects(objectId=newId)
    assert memberships
    membership = memberships[0]
    assert membership.objectId == newId
    assert membership.groupId == protagonists.id


@pytest.fixture(scope="session")
def localHostFqdn():
    return getLocalHostFqdn()


@pytest.fixture(scope="session")
def localWorkbenchPath():
    return 'file:///var/lib/opsi/workbench'


@pytest.fixture(scope="session")
def remoteWorkbenchPath(localHostFqdn):
    return u'smb://%s/opsi_workbench' % localHostFqdn.split('.')[0]


@pytest.fixture
def workbenchConfigServer(localHostFqdn, localWorkbenchPath, remoteWorkbenchPath):
    return OpsiConfigserver(
        id=localHostFqdn,
        workbenchLocalUrl=localWorkbenchPath,
        workbenchRemoteUrl=remoteWorkbenchPath
    )


def testWorkbenchAddressAtDepots(extendedConfigDataBackend, workbenchConfigServer, localWorkbenchPath, remoteWorkbenchPath):
    extendedConfigDataBackend.host_insertObject(workbenchConfigServer)

    serverFromBackend = extendedConfigDataBackend.host_getObjects(id=workbenchConfigServer.id)[0]

    assert serverFromBackend.workbenchLocalUrl == localWorkbenchPath
    assert serverFromBackend.workbenchRemoteUrl == remoteWorkbenchPath

    assert serverFromBackend.getWorkbenchLocalUrl() == localWorkbenchPath
    assert serverFromBackend.getWorkbenchRemoteUrl() == remoteWorkbenchPath


def testWorkbenchAddressAtDepotsInJson(extendedConfigDataBackend, workbenchConfigServer, localWorkbenchPath, remoteWorkbenchPath):
    extendedConfigDataBackend.host_insertObject(workbenchConfigServer)

    serverFromBackend = extendedConfigDataBackend.host_getObjects(id=workbenchConfigServer.id)[0]

    serverDict = serverFromBackend.toHash()
    assert serverDict['workbenchLocalUrl'] == localWorkbenchPath
    assert serverDict['workbenchRemoteUrl'] == remoteWorkbenchPath


def testWorkbenchAddressHasNoDefault(extendedConfigDataBackend, localHostFqdn):
    server = OpsiConfigserver(id=localHostFqdn)
    extendedConfigDataBackend.host_insertObject(server)

    serverFromBackend = extendedConfigDataBackend.host_getObjects(id=server.id)[0]
    assert serverFromBackend.workbenchLocalUrl is None
    assert serverFromBackend.workbenchRemoteUrl is None


@pytest.fixture(
    scope="session",
    params=[30, 64],
    ids=['inventoryNumber-30', 'inventoryNumber-64']
)
def inventoryNumber(request):
    return randomString(request.param)


@pytest.mark.parametrize("hostClass", [OpsiClient, OpsiDepotserver])
def testInventoryNumberOnHosts(configDataBackend, hostClass, inventoryNumber):
    host = hostClass(id='testhost.some.test')
    host.setInventoryNumber(inventoryNumber)

    backend = configDataBackend
    backend.host_insertObject(host)

    hostFromBackend = backend.host_getObjects(id=host.id)[0]

    assert hostFromBackend.inventoryNumber == inventoryNumber
    assert hostFromBackend.getInventoryNumber() == inventoryNumber
