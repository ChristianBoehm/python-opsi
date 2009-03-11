#!/usr/bin/python
# -*- coding: utf-8 -*-
"""
   = = = = = = = = = = = = = = = = = = =
   =   opsi python library - System    =
   = = = = = = = = = = = = = = = = = = =
   
   This module is part of the desktop management solution opsi
   (open pc server integration) http://www.opsi.org
   
   Copyright (C) 2006, 2007, 2008 uib GmbH
   
   http://www.uib.de/
   
   All rights reserved.
   
   This program is free software; you can redistribute it and/or modify
   it under the terms of the GNU General Public License version 2 as
   published by the Free Software Foundation.
   
   This program is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
   GNU General Public License for more details.
   
   You should have received a copy of the GNU General Public License
   along with this program; if not, write to the Free Software
   Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
   
   @copyright:	uib GmbH <info@uib.de>
   @author: Jan Schneider <j.schneider@uib.de>
   @license: GNU General Public License version 2
"""

import os

if (os.name == 'posix'):
	from Posix import *
if (os.name == 'nt'):
	from Windows import *

def rmdir(path, recursive=False):
	try:
		if recursive:
			for root, dirs, files in os.walk(path, topdown=False):
				for name in files:
					os.remove(os.path.join(root, name))
				for name in dirs:
					if os.path.islink( os.path.join(root, name) ):
						os.remove(os.path.join(root, name))
					else:
						os.rmdir(os.path.join(root, name))
		os.rmdir(path)
	except Exception, e:
		raise Exception("Failed to delete directory '%s': %s" % (path, e))

