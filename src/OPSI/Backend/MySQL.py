# -*- coding: utf-8 -*-
"""
   ========================================
   =          OPSI MySQL Module           =
   ========================================
   
   @copyright:	uib - http://www.uib.de - <info@uib.de>
   @author: Patrick Ohler <p.ohler@uib.de>, Jan Schneider <j.schneider@uib.de>
   @license: GNU GPL, see COPYING for details.
"""

__version__ = '0.2'

# Imports
import MySQLdb, warnings, time
from _mysql_exceptions import *

# OPSI imports
from OPSI.Backend.Backend import *
from OPSI.Logger import *

# Get logger instance
logger = Logger()


# ======================================================================================================
# =                                       CLASS MYSQL                                                  =
# ======================================================================================================

class MySQL:
	def __init__(self, username = 'root', password = '', address = 'localhost', database = 'opsi'):
		self.__conn__ = None
		try:
			self.__conn__ = MySQLdb.connect(
							host = address,
							user = username,
							passwd = password,
							db = database,
							use_unicode = True,
							charset = 'utf8' )
		except Exception, e:
			raise BackendIOError("Failed to connect to database '%s' address '%s': %s" % (database, address, e))
		
		self.__cursor__ = self.__conn__.cursor(MySQLdb.cursors.DictCursor)
		
	def db_query(self, query):
		logger.debug2("db_query: %s" % query)
		self.db_execute(query)
		return self.__cursor__.rowcount
		
	def db_getSet(self, query):
		logger.debug2("db_getSet: %s" % query)
		self.db_execute(query)
		valueSet = self.__cursor__.fetchall()
		if not valueSet:
			logger.debug("No result for query '%s'" % query)
			return []
		return valueSet
		
	def db_getRow(self, query):
		logger.debug2("db_getRow: %s" % query)
		self.db_execute(query)
		row = self.__cursor__.fetchone()
		if not row:
			logger.debug("No result for query '%s'" % query)
			return {}
		logger.debug2("Result: '%s'" % row)
		return row
		
	def db_insert(self, table, valueHash):
		colNames = values = ''
		for (key, value) in valueHash.items():
			colNames += "`%s`, " % key
			if type(value) is type(''):
				# String-value
				values += "\'%s\', " % value.replace("'", "\\\'")
			else:
				values += "%s, " % value
		query = "INSERT INTO `%s` (%s) VALUES (%s);" % (table, colNames[:-2], values[:-2])
		logger.debug2("db_insert: %s" % query)
		self.db_execute(query)
		return self.__cursor__.lastrowid
		#return self.__cursor__.rowcount
		
	#def db_update(self, table, valueHash):
	#	pass
	
	def db_execute(self, query):
		if not type(query) is unicode:
			query = unicode(query, 'utf-8')
		return self.__cursor__.execute(query)
	
	def db_info(self):
		return self.__conn__.info()
	
	def db_warning_count(self):
		return self.__conn__.warning_count()
		
	def db_close(self):
		logger.debug("Closing database connection")
		self.__cursor__.close()
		self.__conn__.commit()
		self.__conn__.close()

# ======================================================================================================
# =                                    CLASS MYSQLBACKEND                                              =
# ======================================================================================================
class MySQLBackend(DataBackend):
	
	def __init__(self, username = '', password = '', address = 'localhost', backendManager=None, args={}):
		''' MySQLBackend constructor. '''
		
		self._backendManager = backendManager
		
		# Default values
		self._defaultDomain = 'opsi.org'
		self._username = username
		self._password = password
		self._address = address
		self._database = 'opsi'
		
		# Parse arguments
		for (option, value) in args.items():
			if   (option.lower() == 'database'):		self._database = value
			elif (option.lower() == 'defaultdomain'): 	self._defaultDomain = value
			elif (option.lower() == 'host'):		self._address = value
			elif (option.lower() == 'username'):		self._username = value
			elif (option.lower() == 'password'):		self._password = value
			else:
				logger.warning("Unknown argument '%s' passed to MySQLBackend constructor" % option)
		
		warnings.showwarning = self._showwarning
		self.__mysql__ = MySQL(username = self._username, password = self._password, address = self._address, database = self._database)
		
		
	def _showwarning(self, message, category, filename, lineno, file=None):
		#logger.warning("%s (file: %s, line: %s)" % (message, filename, lineno))
		if str(message).startswith('Data truncated for column'):
			logger.error(message)
		else:
			logger.warning(message)
	
	def _writeToServer_(self, queries):
		for query in queries.split(';'):
			if query.strip():
				self.__mysql__.db_query(query + ' ;')
	
	def createOpsiBase(self):
		# Hardware audit database
		tables = {}
		logger.debug("Current tables:")
		for i in self.__mysql__.db_getSet('SHOW TABLES;'):
			tableName = i.values()[0]
			logger.debug(" [ %s ]" % tableName)
			tables[tableName] = []
			for j in self.__mysql__.db_getSet('SHOW COLUMNS FROM `%s`' % tableName):
				logger.debug("      %s" % j)
				tables[tableName].append(j['Field'])
		
		logger.notice('Creating opsi base')
		
		# Host table
		if not 'HOST' in tables.keys():
			logger.debug('Creating table HOST')
			self._writeToServer_('CREATE TABLE HOST (host_id INT NOT NULL AUTO_INCREMENT, hostId varchar(50) NOT NULL, PRIMARY KEY(`host_id`) ) ENGINE = MYISAM;')
		
		# Hardware audit database (utf-8 encoded)
		opsiHWAuditConf = self.getOpsiHWAuditConf()
		for config in opsiHWAuditConf:
			hwClass = config['Class']['Opsi']
			logger.info("Processing hardware class '%s'" % hwClass)
			
			hardwareDeviceTableName = 'HARDWARE_DEVICE_' + hwClass
			hardwareConfigTableName = 'HARDWARE_CONFIG_' + hwClass
			
			hardwareDeviceTable = 'CREATE TABLE `' + hardwareDeviceTableName + '` (\n' + \
						'`hardware_id` INT NOT NULL AUTO_INCREMENT,\n' + \
						'PRIMARY KEY( `hardware_id` ),\n'
			hardwareConfigTable = 'CREATE TABLE `' + hardwareConfigTableName + '` (\n' + \
						'`config_id` INT NOT NULL AUTO_INCREMENT,\n' + \
						'PRIMARY KEY( `config_id` ),\n' + \
						'`host_id` INT NOT NULL,\n' + \
						'`hardware_id` INT NOT NULL,\n' + \
						'`audit_firstseen` TIMESTAMP NOT NULL DEFAULT \'0000-00-00 00:00:00\',\n' + \
						'`audit_lastseen` TIMESTAMP NOT NULL DEFAULT \'0000-00-00 00:00:00\',\n' + \
						'`audit_state` TINYINT NOT NULL,\n'
			
			hardwareDeviceTableExists = hardwareDeviceTableName in tables.keys()
			hardwareConfigTableExists = hardwareConfigTableName in tables.keys()
			
			if hardwareDeviceTableExists:
				hardwareDeviceTable = 'ALTER TABLE `' + hardwareDeviceTableName + '`\n'
			if hardwareConfigTableExists:
				hardwareConfigTable = 'ALTER TABLE `' + hardwareConfigTableName + '`\n'
			
			for value in config['Values']:
				logger.debug("  Processing value '%s'" % value['Opsi'])
				if   (value['Scope'] == 'g'):
					if hardwareDeviceTableExists:
						if value['Opsi'] in tables[hardwareDeviceTableName]:
							# Column exists => change
							hardwareDeviceTable += 'CHANGE `%s` `%s` %s NULL,\n' % (value['Opsi'], value['Opsi'], value["Type"])
						else:
							# Column does not exist => add
							hardwareDeviceTable += 'ADD `%s` %s NULL,\n' % (value['Opsi'], value["Type"])
					else:
						hardwareDeviceTable += '`%s` %s NULL,\n' % (value['Opsi'], value["Type"])
				elif (value['Scope'] == 'i'):
					if hardwareConfigTableExists:
						if value['Opsi'] in tables[hardwareConfigTableName]:
							# Column exists => change
							hardwareConfigTable += 'CHANGE `%s` `%s` %s NULL,\n' % (value['Opsi'], value['Opsi'], value["Type"])
						else:
							# Column does not exist => add
							hardwareConfigTable += 'ADD `%s` %s NULL,\n' % (value['Opsi'], value["Type"])
					else:
						hardwareConfigTable += '`%s` %s NULL,\n' % (value['Opsi'], value["Type"])
			
			# Remove leading and trailing whitespace
			hardwareDeviceTable = hardwareDeviceTable.strip()
			hardwareConfigTable = hardwareConfigTable.strip()
			
			# Remove trailing comma
			if (hardwareDeviceTable[-1] == ','):
				hardwareDeviceTable = hardwareDeviceTable[:-1]
			if (hardwareConfigTable[-1] == ','):
				hardwareConfigTable = hardwareConfigTable[:-1]
			
			# Finish sql query
			if hardwareDeviceTableExists:
				hardwareDeviceTable += ' ;\n'
			else:
				hardwareDeviceTable += '\n) ENGINE = MYISAM ;\n'
			
			if hardwareConfigTableExists:
				hardwareConfigTable += ' ;\n'
			else:
				hardwareConfigTable += '\n) ENGINE = MYISAM ;\n'
			
			# Log sql query
			logger.debug(hardwareDeviceTable)
			logger.debug(hardwareConfigTable)
			
			# Execute sql query
			self._writeToServer_(hardwareDeviceTable)
			self._writeToServer_(hardwareConfigTable)
		
		# Software audit database
		if not 'SOFTWARE' in tables.keys():
			softwareTable  =  'CREATE TABLE `SOFTWARE` (\n' + \
						'`software_id` INT NOT NULL AUTO_INCREMENT,\n' + \
						'PRIMARY KEY( `software_id` ),\n' + \
						'`softwareId` varchar(100) NOT NULL,\n' + \
						'`displayName` varchar(100),\n' + \
						'`displayVersion` varchar(100),\n' + \
						'`uninstallString` varchar(200),\n' + \
						'`binaryName` varchar(100),\n' + \
						'`installSize` BIGINT\n' + \
					   ') ENGINE = MYISAM ;\n'
			logger.debug(softwareTable)
			self._writeToServer_(softwareTable)
		
		if not 'SOFTWARE_CONFIG' in tables.keys():
			softwareConfigTable  =  'CREATE TABLE `SOFTWARE_CONFIG` (\n' + \
							'`config_id` INT NOT NULL AUTO_INCREMENT,\n' + \
							'PRIMARY KEY( `config_id` ),\n' + \
							'`host_id` INT NOT NULL,\n' + \
							'`software_id` INT NOT NULL,\n' + \
							'`audit_firstseen` TIMESTAMP NOT NULL DEFAULT \'0000-00-00 00:00:00\',\n' + \
							'`audit_lastseen` TIMESTAMP NOT NULL DEFAULT \'0000-00-00 00:00:00\',\n' + \
							'`audit_state` TINYINT NOT NULL,\n' + \
							'`usageFrequency` int NOT NULL DEFAULT -1,\n' + \
							'`lastUsed` TIMESTAMP NOT NULL DEFAULT \'0000-00-00 00:00:00\'\n' + \
						') ENGINE = MYISAM ;\n'
			logger.debug(softwareConfigTable)
			self._writeToServer_(softwareConfigTable)
	
	def getSoftwareInformation_hash(self, hostId):
		hostId = self._preProcessHostId(hostId)
		
		info = {}
		hostDbId = self.__mysql__.db_getRow("SELECT `host_id` FROM `HOST` WHERE `hostId`='%s'" % hostId).get('host_id')
		if not hostDbId:
			logger.warning("No software information found for host '%s'" % hostId)
			return info
		
		# Timestamp of the latest scan
		scantime = time.strptime("2000-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")
		
		for swConfig in self.__mysql__.db_getSet("SELECT * FROM `SOFTWARE_CONFIG` WHERE `audit_state`=1 AND `host_id`=%s" % hostDbId):
			softwareId = ''
			softwareInfo = {}
			
			for (key, value) in swConfig.items():
				if key in ('config_id', 'software_id', 'host_id', 'audit_firstseen', 'audit_state'):
					# Filter out this information
					continue
				if (key == 'audit_lastseen'):
					lastseen = time.strptime(str(value), "%Y-%m-%d %H:%M:%S")
					if (scantime < lastseen):
						scantime = lastseen
					continue
				if (value == None):
					value = ""
				if (key == 'lastUsed'):
					value = str(value)
				if type(value) is unicode:
					value = value.encode('utf-8')
				softwareInfo[key] = value
				
			# Add general hardware device information
			software = self.__mysql__.db_getRow("SELECT * FROM `SOFTWARE` WHERE `software_id`='%s'" % swConfig['software_id'])
			for (key, value) in software.items():
				if key in ('software_id'):
					# Filter out this information
					continue
				if type(value) is unicode:
					value = value.encode('utf-8')
				if key in ('softwareId'):
					softwareId = value
					continue
				if (value == None):
					value = ""
				softwareInfo[key] = value
			
			if softwareId and softwareInfo:
				info[softwareId] = softwareInfo
		
		if not info:
			return info
		info['SCANPROPERTIES'] = {'scantime': time.strftime("%Y-%m-%d %H:%M:%S", scantime) }
		return info
	
	def setSoftwareInformation(self, hostId, info):
		hostId = self._preProcessHostId(hostId)
		if not type(info) is dict:
			raise BackendBadValueError("Software information must be dict")
		
		# Time of scan (may be overwritten by SCANPROPERTIES)
		scantime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
		try:
			scantime = info['SCANPROPERTIES']['scantime']
		except:
			pass
		
		# Is the host already in the db? If yes get id?
		hostDbId = self.__mysql__.db_getRow("SELECT host_id FROM HOST WHERE hostId='%s'" % hostId)
		
		if hostDbId:
			hostDbId = hostDbId['host_id']
		else:
			# Add host to database
			hostDbId = self.__mysql__.db_insert( "HOST", { "hostId": hostId } )
		
		configIdsSeen = []
		
		for (softwareId, softwareInfo) in info.items():
			if (softwareId == 'SCANPROPERTIES'):
				continue
			
			logger.info("Processing softwareId '%s'" % softwareId)
			# This dict contains general (unchangeable) software information
			software = { 'softwareId': softwareId }
			# This dict contains host specific software configuration
			softwareConfig = {}
			
			for (opsiName, opsiValue) in softwareInfo.items():
				if (type(opsiValue) == type(None)):
					continue
				
				if opsiName in ('displayName', 'displayVersion', 'uninstallString', 'installSize', 'binaryName'):
					# This is a general (unchangeable) software information, put it into the software table
					if type(opsiValue) is unicode:
						software[opsiName] = opsiValue.encode('utf-8')
					else:
						software[opsiName] = opsiValue
				else:
					
					# This is a configuration information, put it into the configuration table
					if type(opsiValue) is unicode:
						softwareConfig[opsiName] = opsiValue.encode('utf-8')
					else:
						softwareConfig[opsiName] = opsiValue
					
			# Update / insert hardware device into database
			swId = -1
			query = 'SELECT `software_id` FROM `SOFTWARE` WHERE'
			for (k, v) in software.items():
				if type(v) is type(''):
					# String-value
					query += " `%s` = '%s' AND" % (k, v.replace("'", "\\\'"))
				else:
					query += " `%s` = %s AND" % (k, v)
			query = query[:-4] + ';'
			current = self.__mysql__.db_getSet(query)
			if (len(current) >= 1):
				# Software already exists in database
				logger.debug("Software already in database")
				if (len(current) > 1):
					# Software exists more than once
					swIds = []
					for c in current:
						swIds.append(str(c['software_id']))
					logger.warning("Redundant entries in software database: table 'SOFTWARE', software_ids: %s" \
								% ', '.join(swIds) )
				swId = current[0]['software_id']
			else:
				# Softwaree does not exist in database, create
				logger.info("Adding software to database")
				swId = self.__mysql__.db_insert('SOFTWARE', software)
			
			# Update / insert software configuration into database
			softwareConfig["software_id"] = swId
			softwareConfig["host_id"] = hostDbId
			softwareConfig["audit_firstseen"] = scantime
			softwareConfig["audit_lastseen"] = scantime
			softwareConfig["audit_state"] = 1
			confId = -1
			query = 'SELECT `config_id` FROM `SOFTWARE_CONFIG` WHERE'
			for (k, v) in softwareConfig.items():
				if k in ('audit_firstseen', 'audit_lastseen', 'audit_state'):
					continue
				if k in ('usageFrequency', 'lastUsed'):
					# Update only, do not create new entry in history
					continue
				if type(v) is type(''):
					# String-value
					query += " `%s` = '%s' AND" % (k, v.replace("'", "\\\'"))
				else:
					query += " `%s` = %s AND" % (k, v)
			query = query + " `audit_state`=1 AND `audit_lastseen` != '%s'" % scantime
			current = self.__mysql__.db_getSet(query)
			if (len(current) >= 1):
				# Host specific software config already exists in database
				logger.debug("Host specific software config already in database")
				if (len(current) > 1):
					# Host specific software config exists more than once
					confIds = []
					for c in current:
						confIds.append(str(c['config_id']))
					logger.warning("Redundant entries in software config database: table 'SOFTWARE', config_ids: %s" \
								% ', '.join(confIds) )
				confId = current[0]['config_id']
				# Update config
				self.__mysql__.db_query("UPDATE `SOFTWARE_CONFIG` SET " + \
								"`audit_lastseen`='%s', `usageFrequency`=%d, `lastUsed`='%s' WHERE `config_id` = %d;" \
								% (	scantime, 
									softwareConfig.get('usageFrequency', -1),
									softwareConfig.get('lastUsed', '0000-00-00 00:00:00'),
									confId ) )
			else:
				# Host specific software config does not exist in database, create
				logger.info("Adding host specific software config to database")
				confId = self.__mysql__.db_insert("SOFTWARE_CONFIG", softwareConfig)
			# Add config_id to the list of active software configurations
			configIdsSeen.append(confId)
		
		# Search for inactive software configurations, to mark them as inactive (audit_state 0)
		for config in self.__mysql__.db_getSet('SELECT `config_id` FROM `SOFTWARE_CONFIG` WHERE `audit_state` = 1 AND `host_id` = %d;' % hostDbId):
			if config['config_id'] not in configIdsSeen:
				# This configuration is marked as active but not in the list of active configs, setting audit_state to 0
				logger.notice("Software config with config_id %d vanished (table SOFTWARE_CONFIG), updating audit_state" \
							% config['config_id'])
				self.__mysql__.db_query("UPDATE `SOFTWARE_CONFIG` SET `audit_state` = 0 WHERE `config_id` = %d;" % config['config_id'])
	
	def deleteSoftwareInformation(self, hostId):
		hostId = self._preProcessHostId(hostId)
	
	def getHardwareInformation_listOfHashes(self, hostId):
		return []
	
	def getHardwareInformation_hash(self, hostId):
		hostId = self._preProcessHostId(hostId)
		info = {}
		hostDbId = self.__mysql__.db_getRow("SELECT `host_id` FROM `HOST` WHERE `hostId`='%s'" % hostId).get('host_id')
		if not hostDbId:
			logger.warning("No hardware information found for host '%s'" % hostId)
			return info
		
		# Timestamp of the latest scan
		scantime = time.strptime("2000-01-01 00:00:00", "%Y-%m-%d %H:%M:%S")
		
		for config in self.getOpsiHWAuditConf():
			hwClass = config['Class']['Opsi']
			devices = []
			# Get all active (audit_state=1) hardware configurations of this hardware class and host
			for hwConfig in self.__mysql__.db_getSet("SELECT * FROM `HARDWARE_CONFIG_%s` WHERE `audit_state`=1 AND `host_id`=%s" \
									% (hwClass, hostDbId)):
				device = {}
				for (key, value) in hwConfig.items():
					if key in ('config_id', 'hardware_id', 'host_id', 'audit_firstseen', 'audit_state'):
						# Filter out this information
						continue
					if (key == 'audit_lastseen'):
						lastseen = time.strptime(str(value), "%Y-%m-%d %H:%M:%S")
						if (scantime < lastseen):
							scantime = lastseen
						continue
					if (value == None):
						value = ""
					if type(value) is unicode:
						value = value.encode('utf-8')
					device[key] = value
				
				# Add general hardware device information
				hardware = self.__mysql__.db_getRow("SELECT * FROM `HARDWARE_DEVICE_%s` WHERE `hardware_id`='%s'" % (hwClass, hwConfig['hardware_id']))
				for (key, value) in hardware.items():
					if type(value) is unicode:
						value = value.encode('utf-8')
					if key in ('hardware_id'):
						# Filter out this information
						continue
					if (value == None):
						value = ""
					device[key] = value
				
				if device:
					devices.append(device)
			if devices:
				info[hwClass] = devices
		
		if not info:
			return info
		info['SCANPROPERTIES'] = [ {'scantime': time.strftime("%Y-%m-%d %H:%M:%S", scantime) } ]
		return info
	
	def setHardwareInformation(self, hostId, info):
		hostId = self._preProcessHostId(hostId)
		if not type(info) is dict:
			raise BackendBadValueError("Hardware information must be dict")
		
		# Time of scan (may be overwritten by SCANPROPERTIES)
		scantime = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
		try:
			scantime = info['SCANPROPERTIES'][0]['scantime']
		except:
			pass
		
		# Is the host already in the db? If yes get id?
		hostDbId = self.__mysql__.db_getRow("SELECT host_id FROM HOST WHERE hostId='%s'" % hostId)
		
		if hostDbId:
			hostDbId = hostDbId['host_id']
		else:
			# Add host to database
			hostDbId = self.__mysql__.db_insert( "HOST", { "hostId": hostId } )
		
		# Get and reorganize the opsi hw audit config
		config = self.getOpsiHWAuditConf()
		configNew = {}
		for i in config:
			for j in i['Values']:
				if not configNew.has_key(i['Class']['Opsi']):
					configNew[i['Class']['Opsi']] = {}
				configNew[i['Class']['Opsi']][j['Opsi']] = j['Scope']
		
		queries = ''
		for (hwClass, devices) in info.items():
			if (hwClass == 'SCANPROPERTIES'):
				continue
			
			logger.info("Processing hardware class '%s'" % hwClass)
			
			# This list contains all currently active config_ids of this hardware class and host
			configIdsSeen = []
			
			for device in devices:
				# This dict contains general (unchangeable) hardware device information
				hardwareDevice = {}
				# This dict contains host specific hardware configuration
				hardwareConfig = {}
				
				for (opsiName, opsiValue) in device.items():
					if (type(opsiValue) == type(None)):
						continue
					
					if (configNew[hwClass][opsiName] == 'g'):
						# This is a general (unchangeable) hardware information, put it into the hardware table
						if type(opsiValue) is unicode:
							hardwareDevice[opsiName] = opsiValue.encode('utf-8')
						else:
							hardwareDevice[opsiName] = opsiValue
					else:	
						# This is a configuration information, put it into the configuration table
						if type(opsiValue) is unicode:
							hardwareConfig[opsiName] = opsiValue.encode('utf-8')
						else:
							hardwareConfig[opsiName] = opsiValue
					
				# Update / insert hardware device into database
				hwId = -1
				query = 'SELECT `hardware_id` FROM `HARDWARE_DEVICE_%s` WHERE' % hwClass
				for (k, v) in hardwareDevice.items():
					if type(v) is type(''):
						# String-value
						query += " `%s` = '%s' AND" % (k, v.replace("'", "\\\'"))
					else:
						query += " `%s` = %s AND" % (k, v)
				query = query[:-4] + ';'
				current = self.__mysql__.db_getSet(query)
				if (len(current) >= 1):
					# Hardware device already exists in database
					logger.debug("Hardware device already in database")
					if (len(current) > 1):
						# Hardware device exists more than once
						hwIds = []
						for c in current:
							hwIds.append(str(c['hardware_id']))
						logger.warning("Redundant entries in hardware database: table 'HARDWARE_DEVICE_%s', hardware_ids: %s" \
									% (hwClass, ', '.join(hwIds)) )
					hwId = current[0]['hardware_id']
				else:
					# Hardware device does not exist in database, create
					logger.info("Adding hardware device to database")
					hwId = self.__mysql__.db_insert('HARDWARE_DEVICE_' + hwClass, hardwareDevice)
				
				# Update / insert hardware configuration into database
				hardwareConfig["hardware_id"] = hwId
				hardwareConfig["host_id"] = hostDbId
				hardwareConfig["audit_firstseen"] = scantime
				hardwareConfig["audit_lastseen"] = scantime
				hardwareConfig["audit_state"] = 1
				confId = -1
				query = 'SELECT `config_id` FROM `HARDWARE_CONFIG_%s` WHERE' % hwClass
				for (k, v) in hardwareConfig.items():
					if k in ('audit_firstseen', 'audit_lastseen', 'audit_state'):
						continue
					if type(v) is type(''):
						# String-value
						query += " `%s` = '%s' AND" % (k, v.replace("'", "\\\'"))
					else:
						query += " `%s` = %s AND" % (k, v)
				query = query + " `audit_state`=1 AND `audit_lastseen` != '%s'" % scantime
				current = self.__mysql__.db_getSet(query)
				if (len(current) >= 1):
					# Host specific hardware config already exists in database
					logger.debug("Host specific hardware config already in database")
					if (len(current) > 1):
						# Host specific hardware config exists more than once
						confIds = []
						for c in current:
							confIds.append(str(c['config_id']))
						logger.info("Redundant entries in hardware config database: table 'HARDWARE_CONFIG_%s', config_ids: %s" \
									% (hwClass, ', '.join(confIds)) )
					confId = current[0]['config_id']
					self.__mysql__.db_query("UPDATE `HARDWARE_CONFIG_%s` SET `audit_lastseen`='%s' WHERE `config_id` = %d;" % (hwClass, scantime, confId))
				else:
					# Host specific hardware config does not exist in database, create
					logger.info("Adding host specific hardware config to database")
					confId = self.__mysql__.db_insert("HARDWARE_CONFIG_%s" % hwClass, hardwareConfig)
				# Add config_id to the list of active hardware configurations
				configIdsSeen.append(confId)
			
			# Search for inactive hardware configurations, to mark them as inactive (audit_state 0)
			for config in self.__mysql__.db_getSet('SELECT `config_id` FROM `HARDWARE_CONFIG_%s` WHERE `audit_state` = 1 AND `host_id` = %d;' % (hwClass, hostDbId)):
				if config['config_id'] not in configIdsSeen:
					# This configuration is marked as active but not in the list of active configs, setting audit_state to 0
					logger.notice("Hardware config with config_id %d vanished (table HARDWARE_CONFIG_%s), updating audit_state" \
								% (config['config_id'], hwClass))
					self.__mysql__.db_query("UPDATE `HARDWARE_CONFIG_%s` SET `audit_state` = 0 WHERE `config_id` = %d;" % (hwClass, config['config_id']))
	
	def deleteHardwareInformation(self, hostId):
		hostId = self._preProcessHostId(hostId)
	
	def exit(self):
		self.__mysql__.db_close()





