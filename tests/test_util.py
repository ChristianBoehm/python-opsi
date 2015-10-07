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
Testing functionality of OPSI.Util

:author: Niko Wenselowski <n.wenselowski@uib.de>
:license: GNU Affero General Public License version 3
"""

from __future__ import absolute_import

import codecs
import random
import re
import os
import os.path
import shutil
import unittest
from collections import defaultdict

from OPSI.Util import (chunk, compareVersions, flattenSequence, formatFileSize,
    fromJson, generateOpsiHostKey, getfqdn, getGlobalConfig, ipAddressInNetwork,
    isRegularExpressionPattern, librsyncDeltaFile, librsyncSignature,
    librsyncPatchFile, md5sum, objectToBeautifiedText, objectToHtml,
    randomString, removeUnit, toJson)
from OPSI.Object import LocalbootProduct

from .helpers import (fakeGlobalConf, patchAddress, patchEnvironmentVariables,
    workInTemporaryDirectory)


class IPAddressInNetwork(unittest.TestCase):
    def testNetworkWithSlashIntNotation(self):
        self.assertTrue(ipAddressInNetwork('10.10.1.1', '10.10.0.0/16'))
        self.assertTrue(ipAddressInNetwork('10.10.1.1', '10.10.0.0/23'))
        self.assertFalse(ipAddressInNetwork('10.10.1.1', '10.10.0.0/24'))
        self.assertFalse(ipAddressInNetwork('10.10.1.1', '10.10.0.0/25'))

    def testIpAddressInNetworkWithEmptyNetworkMask(self):
        self.assertTrue(ipAddressInNetwork('10.10.1.1', '0.0.0.0/0'))

    def testIpAddressInNetworkWithFullNetmask(self):
        self.assertTrue(ipAddressInNetwork('10.10.1.1', '10.10.0.0/255.240.0.0'))


class ProductFactory(object):
    productVersions = ('1.0', '2', 'xxx', '3.1', '4')
    packageVersions = ('1', '2', 'y', '3', '10', 11, 22)
    licenseRequirements = (None, True, False)
    setupScripts = ('setup.ins', None)
    updateScripts = ('update.ins', None)
    uninstallScripts = ('uninstall.ins', None)
    alwaysScripts = ('always.ins', None)
    onceScripts = ('once.ins', None)
    priorities = (-100, -90, -30, 0, 30, 40, 60, 99)
    descriptions = ['Test product', 'Some product', '--------', '', None]
    advices = ('Nothing', 'Be careful', '--------', '', None)

    @classmethod
    def generateLocalbootProduct(self, index=0):
        return LocalbootProduct(
            id='product{0}'.format(index),
            productVersion=random.choice(self.productVersions),
            packageVersion=random.choice(self.packageVersions),
            name='Product {0}'.format(index),
            licenseRequired=random.choice(self.licenseRequirements),
            setupScript=random.choice(self.setupScripts),
            uninstallScript=random.choice(self.uninstallScripts),
            updateScript=random.choice(self.updateScripts),
            alwaysScript=random.choice(self.alwaysScripts),
            onceScript=random.choice(self.onceScripts),
            priority=random.choice(self.priorities),
            description=random.choice(self.descriptions),
            advice=random.choice(self.advices),
            changelog=None,
            windowsSoftwareIds=None
        )


class ObjectToHTMLTestCase(unittest.TestCase):
    def testWorkingWithManyObjectsMustNotFail(self):
        obj = [
            ProductFactory.generateLocalbootProduct(i)
            for i in range(1024)
        ]

        objectToHtml(obj, level=0)

    def testCheckingOutput(self):
        product = LocalbootProduct(
            id='htmltestproduct',
            productVersion='3.1',
            packageVersion='1',
            name='Product HTML Test',
            licenseRequired=False,
            setupScript='setup.ins',
            uninstallScript='uninstall.ins',
            updateScript='update.ins',
            alwaysScript='always.ins',
            onceScript='once.ins',
            priority=0,
            description="asdf",
            advice="lolnope",
            changelog=None,
            windowsSoftwareIds=None
        )

        expected = u'{<div style="padding-left: 3em;"><font class="json_key">"onceScript"</font>: "once.ins",<br />\n<font class="json_key">"windowsSoftwareIds"</font>: null,<br />\n<font class="json_key">"description"</font>: "asdf",<br />\n<font class="json_key">"advice"</font>: "lolnope",<br />\n<font class="json_key">"alwaysScript"</font>: "always.ins",<br />\n<font class="json_key">"updateScript"</font>: "update.ins",<br />\n<font class="json_key">"productClassIds"</font>: null,<br />\n<font class="json_key">"id"</font>: "htmltestproduct",<br />\n<font class="json_key">"licenseRequired"</font>: false,<br />\n<font class="json_key">"ident"</font>: "htmltestproduct;3.1;1",<br />\n<font class="json_key">"name"</font>: "Product&nbsp;HTML&nbsp;Test",<br />\n<font class="json_key">"changelog"</font>: null,<br />\n<font class="json_key">"customScript"</font>: null,<br />\n<font class="json_key">"uninstallScript"</font>: "uninstall.ins",<br />\n<font class="json_key">"userLoginScript"</font>: null,<br />\n<font class="json_key">"priority"</font>: 0,<br />\n<font class="json_key">"productVersion"</font>: "3.1",<br />\n<font class="json_key">"packageVersion"</font>: "1",<br />\n<font class="json_key">"type"</font>: "LocalbootProduct",<br />\n<font class="json_key">"setupScript"</font>: "setup.ins"</div>}'
        self.assertEquals(expected, objectToHtml(product))


class ObjectToBeautifiedTextTestCase(unittest.TestCase):
    def testWorkingWithManyObjectsMustNotFail(self):
        obj = [
            ProductFactory.generateLocalbootProduct(i)
            for i in range(10240)
        ]

        objectToBeautifiedText(obj)

    def testCheckingOutput(self):
        product = LocalbootProduct(
            id='htmltestproduct',
            productVersion='3.1',
            packageVersion='1',
            name='Product HTML Test',
            licenseRequired=False,
            setupScript='setup.ins',
            uninstallScript='uninstall.ins',
            updateScript='update.ins',
            alwaysScript='always.ins',
            onceScript='once.ins',
            priority=0,
            description="asdf",
            advice="lolnope",
            changelog=None,
            windowsSoftwareIds=None
        )

        expected = u"""\
[
    {
    "onceScript" : "once.ins",
    "windowsSoftwareIds" : null,
    "description" : "asdf",
    "advice" : "lolnope",
    "alwaysScript" : "always.ins",
    "updateScript" : "update.ins",
    "productClassIds" : null,
    "id" : "htmltestproduct",
    "licenseRequired" : false,
    "ident" : "htmltestproduct;3.1;1",
    "name" : "Product HTML Test",
    "changelog" : null,
    "customScript" : null,
    "uninstallScript" : "uninstall.ins",
    "userLoginScript" : null,
    "priority" : 0,
    "productVersion" : "3.1",
    "packageVersion" : "1",
    "type" : "LocalbootProduct",
    "setupScript" : "setup.ins"
    },
    {
    "onceScript" : "once.ins",
    "windowsSoftwareIds" : null,
    "description" : "asdf",
    "advice" : "lolnope",
    "alwaysScript" : "always.ins",
    "updateScript" : "update.ins",
    "productClassIds" : null,
    "id" : "htmltestproduct",
    "licenseRequired" : false,
    "ident" : "htmltestproduct;3.1;1",
    "name" : "Product HTML Test",
    "changelog" : null,
    "customScript" : null,
    "uninstallScript" : "uninstall.ins",
    "userLoginScript" : null,
    "priority" : 0,
    "productVersion" : "3.1",
    "packageVersion" : "1",
    "type" : "LocalbootProduct",
    "setupScript" : "setup.ins"
    }
]\
"""
        self.maxDiff = None
        self.assertEquals(expected, objectToBeautifiedText([product, product]))

    def testFormattingEmptyList(self):
        self.assertEquals('[\n]', objectToBeautifiedText([]))

    def testFormattingListOfEmptyLists(self):
        expected = u"""\
[
    [
    ],
    [
    ]
]\
"""
        self.assertEquals(expected, objectToBeautifiedText([[],[]]))

    def testFormattingEmptyDict(self):
        self.assertEquals('{\n}', objectToBeautifiedText({}))

        expected = u"""\
    {
    }\
"""
        self.assertEquals(expected, objectToBeautifiedText({}, level=1))

    def testFormattingDefaultDict(self):
        normalDict = {u'lastStateChange': u'', u'actionRequest': u'none', u'productVersion': u'', u'productActionProgress': u'', u'packageVersion': u'', u'installationStatus': u'not_installed', u'productId': u'thunderbird'}
        defaultDict = defaultdict(lambda x: u'')

        for key, value in normalDict.items():
            defaultDict[key] = value

        normal = objectToBeautifiedText(normalDict)
        default = objectToBeautifiedText(defaultDict)

        self.assertEquals(normal, default)


class UtilTestCase(unittest.TestCase):
    """
    General tests for functions in the Util module.
    """
    def test_flattenSequence(self):
        self.assertEqual([1, 2], flattenSequence((1, [2])))
        self.assertEqual([1, 2, 3], flattenSequence((1, [2, (3, )])))
        self.assertEqual([1, 2, 3], flattenSequence(((1, ),(2, ), 3)))
        self.assertEqual([1, 2, 3], flattenSequence(set([1, 2, 3])))
        self.assertEqual([1, 2, 3, 4, 5],
                         flattenSequence([1, set([2,]), 3, 4, set([5])]))

    def test_formatFileSize(self):
        self.assertEqual('123', formatFileSize(123))
        self.assertEqual('1K', formatFileSize(1234))
        self.assertEqual('1M', formatFileSize(1234567))
        self.assertEqual('1G', formatFileSize(1234567890))

    def testRandomString(self):
        self.assertEqual(10, len(randomString(10)))
        self.assertNotEqual('', randomString(1).strip())
        self.assertEqual('', randomString(0).strip())
        self.assertEqual(5*'a', randomString(5, characters='a'))

    def testGenerateOpsiHostKeyIs32CharsLong(self):
        self.assertEqual(32, len(generateOpsiHostKey()))
        self.assertEqual(32, len(generateOpsiHostKey(forcePython=True)))

    def testmd5sum(self):
        testFile = os.path.join(
            os.path.dirname(__file__),
            'testdata', 'util', 'dhcpd', 'dhcpd_1.conf'
        )
        self.assertEqual('5f345ca76574c528903c1022b05acb4c', md5sum(testFile))


class ChunkingTestCase(unittest.TestCase):
    def testChunkingList(self):
        base = list(range(10))

        chunks = chunk(base, size=3)
        self.assertEquals((0, 1, 2), next(chunks))
        self.assertEquals((3, 4, 5), next(chunks))
        self.assertEquals((6, 7, 8), next(chunks))
        self.assertEquals((9, ), next(chunks))
        self.assertRaises(StopIteration, next, chunks)

    def testChunkingGenerator(self):
        def gen():
            yield 0
            yield 1
            yield 2
            yield 3
            yield 4
            yield 5
            yield 6
            yield 7
            yield 8
            yield 9

        chunks = chunk(gen(), size=3)
        self.assertEquals((0, 1, 2), next(chunks))
        self.assertEquals((3, 4, 5), next(chunks))
        self.assertEquals((6, 7, 8), next(chunks))
        self.assertEquals((9, ), next(chunks))
        self.assertRaises(StopIteration, next, chunks)

    def testChunkingGeneratorWithDifferentSize(self):
        def gen():
            yield 0
            yield 1
            yield 2
            yield 3
            yield 4
            yield 5
            yield 6
            yield 7
            yield 8
            yield 9

        chunks = chunk(gen(), size=5)
        self.assertEquals((0, 1, 2, 3, 4), next(chunks))
        self.assertEquals((5, 6, 7, 8, 9), next(chunks))
        self.assertRaises(StopIteration, next, chunks)


class LibrsyncTestCase(unittest.TestCase):

    def testLibrsyncSignatureBase64Encoded(self):
        testFile = os.path.join(
            os.path.dirname(__file__),
            'testdata', 'util', 'syncFiles', 'librsyncSignature.txt'
        )
        self.assertEqual('cnMBNgAACAAAAAAI/6410IBmvH1GKbBN\n', librsyncSignature(testFile))

    def testLibrsyncSignature(self):
        testFile = os.path.join(
            os.path.dirname(__file__),
            'testdata', 'util', 'syncFiles', 'librsyncSignature.txt'
        )
        signature = librsyncSignature(testFile, base64Encoded=False)
        self.assertEqual('rs\x016\x00\x00\x08\x00\x00\x00\x00\x08\xff\xae5\xd0\x80f\xbc}F)\xb0M', signature)

    def testLibrsyncDeltaFile(self):
        testFile = os.path.join(
            os.path.dirname(__file__),
            'testdata', 'util', 'syncFiles', 'librsyncSignature.txt'
        )

        signature = librsyncSignature(testFile, base64Encoded=False)

        with workInTemporaryDirectory() as tempDir:
            deltafile = os.path.join(tempDir, 'delta')

            librsyncDeltaFile(testFile, signature.strip(), deltafile)
            self.assertTrue(os.path.exists(deltafile), "No delta file was created")

            expectedDelta = 'rs\x026F\x00\x04\x8a\x00'
            with open(deltafile, "r") as f:
                self.assertEqual(expectedDelta, f.read())

    def testLibrsyncPatchFileDoesNotAlterIfUnneeded(self):
        baseFile = os.path.join(
            os.path.dirname(__file__),
            'testdata', 'util', 'syncFiles', 'librsyncSignature.txt'
        )

        signature = librsyncSignature(baseFile, False)

        with workInTemporaryDirectory() as tempDir:
            deltaFile = os.path.join(tempDir, 'base.delta')
            librsyncDeltaFile(baseFile, signature, deltaFile)

            self.assertTrue(os.path.exists(deltaFile))
            expectedDelta = "rs\x026F\x00\x04\x8a\x00"
            with open(deltaFile, "rb") as f:
                self.assertEqual(expectedDelta, f.read())

            newFile = os.path.join(tempDir, 'newFile.txt')
            librsyncPatchFile(baseFile, deltaFile, newFile)
            self.assertTrue(os.path.exists(newFile))

            with open(newFile, "r") as newF:
                with open(baseFile, "r") as baseF:
                    self.assertEqual(baseF.readlines(), newF.readlines())

    def testLibrsyncPatchFileCreatesNewFileBasedOnDelta(self):
        baseFile = os.path.join(
            os.path.dirname(__file__),
            'testdata', 'util', 'syncFiles', 'librsyncSignature.txt'
        )

        signature = librsyncSignature(baseFile, False)

        with workInTemporaryDirectory() as tempDir:
            newFile = os.path.join(tempDir, 'oldnew.txt')
            shutil.copy(baseFile, newFile)

            additionalText = u"Und diese Zeile hier macht den Unterschied."

            with codecs.open(newFile, 'a', 'utf-8') as nf:
                nf.write("\n\n{0}\n".format(additionalText))

            deltaFileForNewFile = os.path.join(tempDir, 'newDelta.delta')
            librsyncDeltaFile(newFile, signature, deltaFileForNewFile)
            expectedDelta = (
                'rs\x026B\x04\xb8Die NASA konnte wieder ein Funksignal der '
                'Sonde New Horizons empfangen. Damit scheint sicher, dass '
                'das Man\xc3\xb6ver ein Erfolg war und nun jede Menge Daten '
                'zu erwarten sind. Bis die alle auf der Erde sind, wird es '
                'aber dauern.\n\nDie NASA feiert eine "historische Nacht": '
                'Die Sonde New Horizons ist am Zwergplaneten Pluto '
                'vorbeigeflogen und hat kurz vor drei Uhr MESZ wieder Kontakt '
                'mit der Erde aufgenommen. Jubel, rotwei\xc3\x9fblaue '
                'F\xc3\xa4hnchen und stehende Ovationen pr\xc3\xa4gten die '
                'Stimmung im John Hopkins Labor in Maryland. Digital stellten '
                'sich prominente Gratulanten ein, von Stephen Hawking mit '
                'einer Videobotschaft bis zu US-Pr\xc3\xa4sident Barack Obama '
                'per Twitter.\n\n"Hallo Welt"\n\nDas erste Funksignal New '
                'Horizons nach dem Vorbeiflug am Pluto brachte noch keine '
                'wissenschaftlichen Ergebnisse oder neue Fotos, sondern '
                'Telemetriedaten der Sonde selbst. Das war so geplant. '
                'Aus diesen Informationen geht hervor, dass es New Horizons '
                'gut geht, dass sie ihren Kurs h\xc3\xa4lt und die '
                'vorausberechnete Menge an Speichersektoren belegt ist. '
                'Daraus schlie\xc3\x9fen die Verantwortlichen der NASA, dass '
                'auch tats\xc3\xa4chlich wissenschaftliche Informationen im '
                'geplanten Ausma\xc3\x9f gesammelt wurden.\n\nUnd diese Zeile '
                'hier macht den Unterschied.\n\x00')

            with open(deltaFileForNewFile, "rb") as f:
                self.assertEqual(expectedDelta, f.read())

            fileBasedOnDelta = os.path.join(tempDir, 'newnew.txt')
            librsyncPatchFile(baseFile, deltaFileForNewFile, fileBasedOnDelta)
            with open(newFile, "r") as newF:
                with open(fileBasedOnDelta, "r") as newF2:
                    self.assertEqual(newF.readlines(), newF2.readlines())

            with codecs.open(fileBasedOnDelta, "r", 'utf-8') as newF2:
                for line in newF2:
                    if additionalText in line:
                        break
                else:
                    self.fail("Missing additional text in new file.")


class CompareVersionTestCase(unittest.TestCase):
    def testComparingVersionsOfSameSize(self):
        self.assertTrue(compareVersions('1.0', '<', '2.0'))

    def testComparingWithoutGivingOperatorDefaultsToEqual(self):
        self.assertTrue(compareVersions('1.0', '', '1.0'))
        self.assertFalse(compareVersions('1', '', '2'))

    def testComparingWithOneEqualitySignWork(self):
        self.assertTrue(compareVersions('1.0', '=', '1.0'))

    def testUsingUnknownOperatorFails(self):
        self.assertRaises(Exception, compareVersions, '1', 'asdf', '2')
        self.assertRaises(Exception, compareVersions, '1', '+-', '2')
        self.assertRaises(Exception, compareVersions, '1', '<>', '2')
        self.assertRaises(Exception, compareVersions, '1', '!=', '2')

    def testIgnoringVersionsWithWaveInThem(self):
        self.assertTrue(compareVersions('1.0~20131212', '<', '2.0~20120101'))
        self.assertTrue(compareVersions('1.0~20131212', '==', '1.0~20120101'))

    def testUsingInvalidVersionStringsFails(self):
        self.assertRaises(Exception, compareVersions, 'abc-1.2.3-4', '==', '1.2.3-4')
        self.assertRaises(Exception, compareVersions, '1.2.3-4', '==', 'abc-1.2.3-4')

    def testComparingWorksWithLettersInVersionString(self):
        self.assertTrue(compareVersions('1.0.a', '<', '1.0.b'))
        self.assertTrue(compareVersions('a.b', '>', 'a.a'))

    def testComparisonsWithDifferntDepthsAreMadeTheSameDepth(self):
        self.assertTrue(compareVersions('1.1.0.1', '>', '1.1'))
        self.assertTrue(compareVersions('1.1', '<', '1.1.0.1'))

    def testPackageVersionsAreComparedAswell(self):
        self.assertTrue(compareVersions('1-2', '<', '1-3'))
        self.assertTrue(compareVersions('1-2.0', '<', '1-2.1'))


class GetGlobalConfigTestCase(unittest.TestCase):
    def setUp(self):
        self.testFile = os.path.join(
            os.path.dirname(__file__), 'testdata', 'util', 'fake_global.conf'
        )

    def tearDown(self):
        del self.testFile

    def testCommentsAreIgnored(self):
        self.assertEqual("no", getGlobalConfig('comment', self.testFile))

    def testLinesNeedAssignments(self):
        self.assertEqual(None, getGlobalConfig('this', self.testFile))

    def testReadingValues(self):
        self.assertEqual("value", getGlobalConfig('keyword', self.testFile))
        self.assertEqual(
            "this works too",
            getGlobalConfig('value with spaces', self.testFile)
        )
        self.assertEqual(
            "we even can include a = and it works",
            getGlobalConfig('advanced value', self.testFile)
        )

    def testFileNotFoundExitsGracefully(self):
        self.assertEqual(None, getGlobalConfig('dontCare', 'nonexistingFile'))


class IsRegularExpressionTestCase(unittest.TestCase):
    def testIfIsRegExObject(self):
        self.assertFalse(isRegularExpressionPattern("no pattern"))
        self.assertFalse(isRegularExpressionPattern("SRE_Pattern"))

        self.assertTrue(isRegularExpressionPattern(re.compile("ABC")))


class RemoveUnitTestCase(unittest.TestCase):
    def testNoUnitMeansNoRemoval(self):
        self.assertEquals(2, removeUnit(2))
        self.assertEquals(2, removeUnit('2'))

    def testRemovingMegabyte(self):
        self.assertEquals(2048 * 1024, removeUnit('2MB'))


class GetFQDNTestCase(unittest.TestCase):

    def testGettingFQDN(self):
        fqdn = "opsi.fqdntestcase.invalid"

        with patchAddress(fqdn=fqdn):
            self.assertEqual(fqdn, getfqdn())

    def testGettingFQDNFromGlobalConfig(self):
        with patchAddress(fqdn="nomatch.opsi.invalid"):
            fqdn = "opsi.test.invalid"
            with fakeGlobalConf(fqdn=fqdn) as configPath:
                self.assertEqual(fqdn, getfqdn(conf=configPath))

    def testGettingFQDNIfConfigMissing(self):
        fqdn = "opsi.fqdntestcase.invalid"

        configFilePath = randomString(32)
        while os.path.exists(configFilePath):
            configFilePath = randomString(32)

        with patchAddress(fqdn=fqdn):
            self.assertEqual(fqdn, getfqdn(conf=configFilePath))

    def testGettingFQDNIfConfigEmpty(self):
        with workInTemporaryDirectory() as tempDir:
            fqdn = "opsi.fqdntestcase.invalid"
            with patchAddress(fqdn=fqdn):
                confPath = os.path.join(tempDir, randomString(8))
                with open(confPath, 'w') as conf:
                    pass

                self.assertEqual(fqdn, getfqdn(conf=confPath))

    def testGettingFQDNFromEnvironment(self):
        fqdn = "opsi.fqdntestcase.invalid"
        with patchAddress(fqdn="nomatch.uib.local"):
            with patchEnvironmentVariables(OPSI_HOSTNAME=fqdn):
                self.assertEqual(fqdn, getfqdn())

    def testGetFQDNByIPAddress(self):
        fqdn = "opsi.fqdntestcase.invalid"
        address = '127.0.0.1'

        with patchAddress(fqdn=fqdn, address=address):
            self.assertEqual(fqdn, getfqdn(name=address))


class JSONSerialisiationTestCase(unittest.TestCase):
    def testSerialisingSet(self):
        input = set([u'opsi-client-agent', u'apple_itunes', u'nodejs', u'adobe_reader', u'microsoft_vc_2010', u'adobe_flash_activex', u'image-einrichtung', u'dbvisualizer', u'mozillafirefox', u'java_jre8_x64', u'apple_mobile_device_support', u'paintnet', u'googledrive', u'apple_application_support', u'deploy_modifications', u'swaudit', u'python', u'admintools_hash_and_crc', u'shutdownwanted', u'inventory', u'hwaudit', u'libreoffice', u'teamviewer10', u'languagepacks', u'apple_bonjour', u'admintools_wuinstall', u'java_jre8_x86', u'adobe_acrobat_x', u'googlechrome', u'tortoise_git', u'java_jre7_x86', u'cdburnerxp', u'apple_quicktime', u'adobe_air', u'inventarisierung_silent', u'python3', u'mysysgit', u'java_jre7_x64', u'opsi-winst', u'setacl', u'adobe_flash_pluginbased', u'tortoise_svn', u'admintools_virtualbox', u'windows_config'])

        output = toJson(input)

        self.assertEquals(set(fromJson(output)), input)


if __name__ == '__main__':
    unittest.main()
