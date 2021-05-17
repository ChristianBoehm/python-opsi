# -*- coding: utf-8 -*-

# This file is part of python-opsi.
# Copyright (C) 2015-2018 uib GmbH <info@uib.de>

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
Testing the work with repositories.

:author: Niko Wenselowski <n.wenselowski@uib.de>
:author: Erol Ueluekmen <e.ueluekmen@uib.de>
:license: GNU Affero General Public License version 3
"""

import os
import pytest

from OPSI.Exceptions import RepositoryError
from OPSI.Util.Repository import FileRepository, getRepository, getFileInfosFromDavXML


def testGettingFileRepository():
	repo = getRepository("file:///not-here")
	assert isinstance(repo, FileRepository)


def testGettingRepositoryFailsOnUnsupportedURL():
	with pytest.raises(RepositoryError):
		getRepository("lolnope:///asdf")


def testListingRepository(tempDir):
	repo = FileRepository(url=u'file://{path}'.format(path=tempDir))
	assert not repo.content('', recursive=True)

	os.mkdir(os.path.join(tempDir, "foobar"))

	assert 1 == len(repo.content('', recursive=True))
	for content in repo.content('', recursive=True):
		assert content == {'path': u'foobar', 'type': 'dir', 'name': u'foobar', 'size': 0}

	with open(os.path.join(tempDir, "bar"), "w"):
		pass

	assert 2 == len(repo.content('', recursive=True))
	assert 2 == len(repo.listdir())
	assert "bar" in repo.listdir()

	# TODO: list subdir tempDir and check if file is shown


def testFileRepositoryFailsWithWrongURL():
	with pytest.raises(RepositoryError):
		FileRepository(u'nofile://nada')


@pytest.fixture
def twistedDAVXMLPath():
	return os.path.join(
		os.path.dirname(__file__),
		'testdata', 'util', 'davxml', 'twisted-davxml.data')


@pytest.fixture
def twistedDAVXML(twistedDAVXMLPath):
	with open(twistedDAVXMLPath, 'r') as f:
		return f.read()


def testGetFileInfosFromDavXML(twistedDAVXML):
	content = getFileInfosFromDavXML(twistedDAVXML)
	assert len(content) == 4

	dirs = 0
	files = 0
	for item in content:
		assert isinstance(item['size'], int)
		if item['type'] == 'dir':
			dirs = dirs + 1
		elif item['type'] == 'file':
			files = files + 1
		else:
			raise ValueError("Unexpected type {!r} found. Maybe creepy testdata?".format(item['type']))

	assert dirs == 1
	assert files == 3

def test_file_repo_start_end(tmpdir):
	src_dir = tmpdir.mkdir("src")
	src = src_dir.join("test.txt")
	src.write("123456789")
	dst_dir = tmpdir.mkdir("dst")
	dst = dst_dir.join("test.txt")

	repo = getRepository(f"file://{src_dir}")
	repo.download("test.txt", str(dst), startByteNumber=-1, endByteNumber=-1)
	assert dst.read() == "123456789"

	repo.download("test.txt", str(dst), startByteNumber=0, endByteNumber=-1)
	assert dst.read() == "123456789"

	repo.download("test.txt", str(dst), startByteNumber=0, endByteNumber=1)
	assert dst.read() == "1"

	repo.download("test.txt", str(dst), startByteNumber=1, endByteNumber=1)
	assert dst.read() == ""

	repo.download("test.txt", str(dst), startByteNumber=0, endByteNumber=2)
	assert dst.read() == "12"

	repo.download("test.txt", str(dst), startByteNumber=5, endByteNumber=9)
	assert dst.read() == "6789"

