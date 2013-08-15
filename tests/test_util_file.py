#!/usr/bin/env python
#-*- coding: utf-8 -*-

import os
import shutil
import tempfile
import unittest

from OPSI.Util.File import IniFile, InfFile, TxtSetupOemFile


def copyTestfileToTemporaryFolder(filename):
    temporary_folder = tempfile.mkdtemp()
    shutil.copy(filename, temporary_folder)

    (_, new_filename) = os.path.split(filename)

    return os.path.join(temporary_folder, new_filename)


class ParseIniFileTestCase(unittest.TestCase):
    def test_parsing_does_not_fail(self):
        iniTestData = '''
#[section1]
# abc = def

[section2]
abc = def # comment

[section3]
key = value ;comment ; comment2

[section4]
key = value \; no comment \# comment2 ;# comment3

[section5]
key = \;\;\;\;\;\;\;\;\;\;\;\;
        '''

        iniFile = IniFile('filename_is_irrelevant_for_this')
        iniFile.parse(iniTestData.split('\n'))


class ParseInfFileTestCase(unittest.TestCase):
    def setUp(self):
        pathToConfig = os.path.join(os.path.dirname(__file__), 'testdata',
                                    'util', 'file', 'inf_testdata_8.inf')
        infFile = InfFile(pathToConfig)
        infFile.parse()
        self.devices = infFile.getDevices()

    def tearDown(self):
        del self.devices

    def testDevicesAreRead(self):
        devices = self.devices

        self.assertNotEqual(None, devices)
        self.assertNotEqual([], devices)
        self.assertTrue(bool(devices), 'No devices found.')

    def test_device_data_is_correct(self):
        devices = self.devices

        for dev in devices:
            self.assertNotEqual(None, dev['vendor'])
            self.assertNotEqual(None, dev['device'])


class CopySetupOemFileTestsMixin(object):
    TEST_DATA_FOLDER = os.path.join(
        os.path.dirname(__file__), 'testdata', 'util', 'file',
    )
    ORIGINAL_SETUP_FILE = None

    def setUp(self):
        oemSetupFile = copyTestfileToTemporaryFolder(
            os.path.join(self.TEST_DATA_FOLDER, self.ORIGINAL_SETUP_FILE)
        )

        self.txtSetupOemFile = TxtSetupOemFile(oemSetupFile)
        self.txtSetupOemFile.parse()

    def tearDown(self):
        testDirectory = os.path.dirname(self.txtSetupOemFile.getFilename())
        if (os.path.exists(testDirectory)
            and (os.path.normpath(self.TEST_DATA_FOLDER) !=
                 os.path.normpath(testDirectory))):
            shutil.rmtree(testDirectory)

        del self.txtSetupOemFile

    def testGenerationDoesNotFail(self):
        self.txtSetupOemFile.generate()


class ApplyingWorkaroundsTestsMixin(object):
    COMMENT_CHARACTERS = (';', '#')

    def testApplyingWorkaroundsRemovesComments(self):
        self.txtSetupOemFile.applyWorkarounds()
        self.txtSetupOemFile.generate()

        with open(self.txtSetupOemFile.getFilename()) as setupfile:
            for line in setupfile:
                for comment_char in self.COMMENT_CHARACTERS:
                    self.assertFalse(
                        line.startswith(';'),
                        'Line starts with character "{c}"" but should not: '
                        '{line}'.format(line=line, c=comment_char)
                    )

    def testApplyingWorkaroundsCreatesDisksSection(self):
        self.txtSetupOemFile.applyWorkarounds()
        self.txtSetupOemFile.generate()

        self.searchForSection('[Disks]')

    def searchForSection(self, sectionName):
        sectionFound = False

        with open(self.txtSetupOemFile.getFilename()) as setupfile:
            for line in setupfile:
                sectionFound = sectionName in line

                if sectionFound:
                    break

        self.assertTrue(
            sectionFound,
            'Expected sektion "{0}" inside the setup file.'.format(sectionName)
        )

    def testApplyingWorkaroundsCreatesDefaultsSection(self):
        self.txtSetupOemFile.applyWorkarounds()
        self.txtSetupOemFile.generate()

        self.searchForSection('[Defaults]')

    def testCommasAreFollowdBySpace(self):
        self.txtSetupOemFile.applyWorkarounds()
        self.txtSetupOemFile.generate()

        with open(self.txtSetupOemFile.getFilename()) as setupfile:
            for line in setupfile:
                if ',' in line:
                    commaIndex = line.index(',')
                    self.assertEqual(
                        ' ',
                        line[commaIndex + 1],
                        'Expected a space after the comma at position {i} in '
                        'line: {l}'.format(i=commaIndex, l=line)
                    )

    def testApplyingWorkaroundsChangesContents(self):
        with open(self.txtSetupOemFile.getFilename()) as setupfile:
            before = setupfile.readlines()

        self.txtSetupOemFile.applyWorkarounds()
        self.txtSetupOemFile.generate()

        with open(self.txtSetupOemFile.getFilename()) as setupfile:
            after = setupfile.readlines()

        self.assertNotEqual(before, after)


class ApplyingWorkaroundsForExistingIDsMixin(ApplyingWorkaroundsTestsMixin):
    EXISTING_VENDOR_AND_DEVICE_IDS = ((None, None), )  # example to show format

    def testReadingInSpecialDevicesAndApplyingFixes(self):
        for (vendorId, deviceId) in self.EXISTING_VENDOR_AND_DEVICE_IDS:
            self.assertTrue(
                self.txtSetupOemFile.isDeviceKnown(
                    vendorId=vendorId,
                    deviceId=deviceId
                ),
                'No device found for vendor "{0}" and device ID '
                '"{1}"'.format(vendorId, deviceId)
            )

            self.assertNotEqual(
                [],
                self.txtSetupOemFile.getFilesForDevice(
                    vendorId=vendorId,
                    deviceId=deviceId,
                    fileTypes=[]
                ),
                'Could not find files for vendor "{0}" and device ID '
                '"{1}"'.format(vendorId, deviceId)
            )

            self.assertTrue(
                bool(
                    self.txtSetupOemFile.getComponentOptionsForDevice(vendorId=vendorId, deviceId=deviceId)['description']
                )
            )

            self.txtSetupOemFile.applyWorkarounds()
            self.txtSetupOemFile.generate()

            self.assertNotEqual(
                [],
                self.txtSetupOemFile.getFilesForDevice(
                    vendorId=vendorId,
                    deviceId=deviceId,
                    fileTypes=[]
                )
            )

class ApplyingWorkaroundsForNonExistingIDsMixin(ApplyingWorkaroundsTestsMixin):
    NON_EXISTING_VENDOR_AND_DEVICE_IDS = ((None, None), )  # example to show format

    def testReadingInSpecialDevicesAndApplyingFixes(self):
        for (vendorId, deviceId) in self.NON_EXISTING_VENDOR_AND_DEVICE_IDS:
            self.assertFalse(
                self.txtSetupOemFile.isDeviceKnown(
                    vendorId=vendorId,
                    deviceId=deviceId
                ),
                'Device found for vendor "{0}" and device ID "{1}"'.format(vendorId, deviceId)
            )

            self.assertRaises(
                Exception,
                self.txtSetupOemFile.getFilesForDevice,
                vendorId=vendorId,
                deviceId=deviceId,
                fileTypes=[]
            )

            self.assertRaises(
                Exception,
                self.txtSetupOemFile.getComponentOptionsForDevice,
                vendorId=vendorId,
                deviceId=deviceId
            )

            self.txtSetupOemFile.applyWorkarounds()
            self.txtSetupOemFile.generate()

            self.assertRaises(
                Exception,
                self.txtSetupOemFile.getFilesForDevice,
                vendorId=vendorId,
                deviceId=deviceId,
                fileTypes=[]
            )


class DeviceDataTestsMixin(object):
    def testDevicesContents(self):
        devices = self.txtSetupOemFile.getDevices()

        for device in devices:
            self.assertNotEqual(None, device['vendor'],
                'The vendor should be set but isn\'t: {0}'.format(device))
            self.assertNotEqual(None, device['device'])

    def testDevicesAreRead(self):
        devices = self.txtSetupOemFile.getDevices()

        self.assertTrue(bool(devices), 'No devices found!')


class SetupOemTestCase1(CopySetupOemFileTestsMixin,
                        unittest.TestCase,
                        ApplyingWorkaroundsForExistingIDsMixin,
                        DeviceDataTestsMixin):

    ORIGINAL_SETUP_FILE = 'txtsetupoem_testdata_1.oem'
    EXISTING_VENDOR_AND_DEVICE_IDS = (('10DE', '07F6'), )


class SetupOemTestCase2(CopySetupOemFileTestsMixin,
                        unittest.TestCase,
                        ApplyingWorkaroundsForNonExistingIDsMixin,
                        DeviceDataTestsMixin):
    ORIGINAL_SETUP_FILE = 'txtsetupoem_testdata_2.oem'
    NON_EXISTING_VENDOR_AND_DEVICE_IDS = (('10DE', '07F6'), )


class SetupOemTestCase3(CopySetupOemFileTestsMixin,
                        unittest.TestCase,
                        ApplyingWorkaroundsForExistingIDsMixin,
                        DeviceDataTestsMixin):

    ORIGINAL_SETUP_FILE = 'txtsetupoem_testdata_3.oem'
    EXISTING_VENDOR_AND_DEVICE_IDS = (('10DE', '07F6'), )


class SetupOemTestCase4(CopySetupOemFileTestsMixin,
                        unittest.TestCase,
                        ApplyingWorkaroundsForExistingIDsMixin,
                        DeviceDataTestsMixin):
    ORIGINAL_SETUP_FILE = 'txtsetupoem_testdata_4.oem'
    EXISTING_VENDOR_AND_DEVICE_IDS = (('1002', '4391'), )

    def testReadingDataFromTextfile(self):
        self.assertFalse(
            self.txtSetupOemFile.isDeviceKnown(
                vendorId='10DE',
                deviceId = '0AD4'
            )
        )

        self.assertRaises(
            Exception,
            self.txtSetupOemFile.getFilesForDevice,
            vendorId='10DE',
            deviceId='0AD4',
            fileTypes=[]
        )

        self.assertRaises(
            Exception,
            self.txtSetupOemFile.getFilesForDevice,
            vendorId='10DE',
            deviceId='07F6',
            fileTypes=[]
        )

        self.assertFalse(
            self.txtSetupOemFile.isDeviceKnown(
                vendorId='10DE',
                deviceId = '0754'
            )
        )

        self.assertRaises(
            Exception,
            self.txtSetupOemFile.getComponentOptionsForDevice,
            vendorId='10DE',
            deviceId = '0AD4'
        )


class SetupOemTestCase5(CopySetupOemFileTestsMixin,
                        unittest.TestCase,
                        ApplyingWorkaroundsForNonExistingIDsMixin):
    ORIGINAL_SETUP_FILE = 'txtsetupoem_testdata_5.oem'
    NON_EXISTING_VENDOR_AND_DEVICE_IDS = (('10DE', '07F6'), )

    def testReadingDataFromTextfile(self):
        self.assertFalse(
            self.txtSetupOemFile.isDeviceKnown(
                vendorId='10DE',
                deviceId = '0AD4'
            )
        )

        self.assertRaises(
            Exception,
            self.txtSetupOemFile.getFilesForDevice,
            vendorId='10DE',
            deviceId='07F6',
            fileTypes=[]
        )

        self.assertFalse(
            self.txtSetupOemFile.isDeviceKnown(
                vendorId='10DE',
                deviceId = '0754'
            )
        )

        self.assertRaises(
            Exception,
            self.txtSetupOemFile.getComponentOptionsForDevice,
            vendorId='10DE',
            deviceId = '0AD4'
        )

    def testDevicesContents(self):
        devices = self.txtSetupOemFile.getDevices()

        for device in devices:
            self.assertNotEqual(None, device['vendor'],
                'The vendor should be set but isn\'t: {0}'.format(device))
            self.assertEqual('fttxr5_O', device['serviceName'])


class SetupOemTestCase6(CopySetupOemFileTestsMixin,
                        unittest.TestCase,
                        ApplyingWorkaroundsForNonExistingIDsMixin,
                        DeviceDataTestsMixin):
    ORIGINAL_SETUP_FILE = 'txtsetupoem_testdata_6.oem'
    NON_EXISTING_VENDOR_AND_DEVICE_IDS = (('10DE', '07F6'), )

    def testReadingDataFromTextfile(self):
        self.assertFalse(
            self.txtSetupOemFile.isDeviceKnown(
                vendorId='10DE',
                deviceId = '0AD4'
            )
        )

        self.assertRaises(Exception,
            self.txtSetupOemFile.getFilesForDevice,
            vendorId='10DE',
            deviceId='0AD4',
            fileTypes=[]
        )

        self.assertRaises(
            Exception,
            self.txtSetupOemFile.getFilesForDevice,
            vendorId='10DE',
            deviceId='07F6',
            fileTypes=[]
        )

        self.assertFalse(
            self.txtSetupOemFile.isDeviceKnown(
                vendorId='10DE',
                deviceId = '0754'
            )
        )

        self.assertRaises(
            Exception,
            self.txtSetupOemFile.getComponentOptionsForDevice,
            vendorId='10DE',
            deviceId = '0AD4'
        )


class SetupOemTestCase7(CopySetupOemFileTestsMixin,
                        unittest.TestCase,
                        ApplyingWorkaroundsForExistingIDsMixin,
                        DeviceDataTestsMixin):
    ORIGINAL_SETUP_FILE = 'txtsetupoem_testdata_7.oem'
    EXISTING_VENDOR_AND_DEVICE_IDS = (('8086', '3B22'), )

    def testReadingDataFromTextfile(self):
        self.assertFalse(
            self.txtSetupOemFile.isDeviceKnown(
                vendorId='10DE',
                deviceId = '0AD4'
            )
        )

        self.assertRaises(Exception,
            self.txtSetupOemFile.getFilesForDevice,
            vendorId='10DE',
            deviceId='0AD4',
            fileTypes=[]
        )

        self.assertRaises(Exception,
            self.txtSetupOemFile.getFilesForDevice,
            vendorId='10DE',
            deviceId='07F6',
            fileTypes=[]
        )

        self.assertFalse(
            self.txtSetupOemFile.isDeviceKnown(
                vendorId='10DE',
                deviceId = '0754'
            )
        )

        self.assertRaises(
            Exception,
            self.txtSetupOemFile.getComponentOptionsForDevice,
            vendorId='10DE',
            deviceId = '0AD4'
        )


if __name__ == '__main__':
    unittest.main()
