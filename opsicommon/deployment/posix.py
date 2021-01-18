import sys
import os
from contextlib import closing, contextmanager

from OPSI.Util.File import IniFile
from OPSI.Util import randomString
from OPSI.Types import forceUnicode, forceUnicodeLower
from OPSI.System import copy
from OPSI.Object import ProductOnClient

from .common import logger, DeployThread, SkipClientException, SKIP_MARKER
from .common import socket, re

try:
	import paramiko	# type: ignore
	AUTO_ADD_POLICY = paramiko.AutoAddPolicy
	WARNING_POLICY = paramiko.WarningPolicy
	REJECT_POLICY = paramiko.RejectPolicy
except ImportError:
	paramiko = None
	AUTO_ADD_POLICY = None
	WARNING_POLICY = None
	REJECT_POLICY = None

class SSHRemoteExecutionException(Exception):
	pass

class LinuxDeployThread(DeployThread):
	def __init__(self, host, backend, username, password, shutdown, reboot, startService,
		deploymentMethod="hostname", stopOnPingFailure=True,
		skipExistingClient=False, mountWithSmbclient=True,
		keepClientOnFailure=False, additionalClientSettings=None,
		depot=None, group=None, sshPolicy=WARNING_POLICY):

		DeployThread.__init__(self, host, backend, username, password, shutdown,
		reboot, startService, deploymentMethod, stopOnPingFailure,
		skipExistingClient, mountWithSmbclient, keepClientOnFailure,
		additionalClientSettings, depot, group)

		self._sshConnection = None
		self._sshPolicy = sshPolicy

	def run(self):
		self._installWithSSH()

	def _installWithSSH(self):
		logger.debug('Installing with files copied to client via scp.')
		host = forceUnicodeLower(self.host)
		hostId = ''
		hostObj = None
		remoteFolder = os.path.join('/tmp', 'opsi-linux-client-agent')
		try:
			hostId = self._getHostId(host)
			self._checkIfClientShouldBeSkipped(hostId)

			logger.notice("Starting deployment to host %s", hostId)
			hostObj = self._prepareDeploymentToHost(hostId)

			if getattr(sys, 'frozen', False):
				localFolder = os.path.dirname(os.path.abspath(sys.executable))		# for running as executable
			else:
				localFolder = os.path.dirname(os.path.abspath(__file__))			# for running from python
			logger.notice("Patching config.ini")
			configIniName = f'{randomString(10)}_config.ini')
			configIniPath = os.path.join('/tmp', configIniName)
			copy(os.path.join(localFolder, 'files', 'opsi', 'cfg', 'config.ini'), configIniPath)
			configFile = IniFile(configIniPath)
			config = configFile.parse()
			if not config.has_section('shareinfo'):
				config.add_section('shareinfo')
			config.set('shareinfo', 'pckey', hostObj.opsiHostKey)
			if not config.has_section('general'):
				config.add_section('general')
			config.set('general', 'dnsdomain', '.'.join(hostObj.id.split('.')[1:]))
			configFile.generate(config)
			logger.debug("Generated config.")

			try:
				logger.notice("Copying installation scripts...")
				self._copyDirectoryOverSSH(
					os.path.join(localFolder, 'files'),
					remoteFolder
				)

				logger.debug("Copying config for client...")
				self._copyFileOverSSH(configIniPath, os.path.join(remoteFolder, 'files', 'opsi', 'cfg', 'config.ini'))

				logger.debug("Checking architecture of client...")
				remoteArch = self._getTargetArchitecture()
				if not remoteArch:
					raise RuntimeError("Could not get architecture of client.")

				opsiscript = f"/tmp/opsi-linux-client-agent/files/opsi/opsi-script/{remoteArch}/opsi-script"
				logger.debug("Will use: %s", opsiscript)
				self._executeViaSSH(f"chmod +x {opsiscript}")

				installCommand = f"{opsiscript} -batch -silent /tmp/opsi-linux-client-agent/files/opsi/setup.opsiscript /var/log/opsi-client-agent/opsi-script/opsi-client-agent.log -PARAMETER REMOTEDEPLOY"
				nonrootExecution = self.username != 'root'
				credentialsfile=None
				if nonrootExecution:
					credentialsfile = os.path.join(remoteFolder, '.credentials')
					self._executeViaSSH(f"touch {credentialsfile}")
					self._executeViaSSH(f"chmod 600 {credentialsfile}")
					self._executeViaSSH(f"echo '{self.password}' > {credentialsfile}")
					self._executeViaSSH(f'echo "\n" >> {credentialsfile}')
					installCommand = f"sudo --stdin -- {installCommand} < {credentialsfile}"

				try:
					logger.notice('Running installation script...')
					self._executeViaSSH(installCommand)
				except Exception:
					if nonrootExecution:
						self._executeViaSSH(f"rm -f {credentialsfile}")
					raise

				logger.debug("Testing if folder was created...")
				self._executeViaSSH("test -d /etc/opsi-client-agent/")
				logger.debug("Testing if config can be found...")
				checkCommand = "test -e /etc/opsi-client-agent/opsiclientd.conf"
				if nonrootExecution:
					# This call is executed with sudo, because etc/opsi-client-agent belongs to root:root
					checkCommand = f"sudo --stdin -- {checkCommand} < {credentialsfile}"
				self._executeViaSSH(checkCommand)

				logger.debug("Testing if executable was found...")
				self._executeViaSSH("test -e /usr/bin/opsiclientd -o -e /usr/bin/opsi-script-nogui")
			finally:
				try:
					os.remove(configIniPath)
				except OSError as error:
					logger.debug("Removing %s failed: %s", configIniPath, error)

			logger.notice("opsi-linux-client-agent successfully installed on %s", hostId)
			self.success = True
			self._setOpsiClientAgentToInstalled(hostId)
			self._finaliseInstallation(credentialsfile=credentialsfile)
		except SkipClientException:
			logger.notice("Skipping host %s", hostId)
			self.success = SKIP_MARKER
			return
		except (Exception, paramiko.SSHException) as error:
			logger.error("Deployment to %s failed: %s", self.host, error)
			self.success = False
			if 'Incompatible ssh peer (no acceptable kex algorithm)' in forceUnicode(error):
				logger.error('Please install paramiko v1.15.1 or newer.')

			if self._clientCreatedByScript and hostObj and not self.keepClientOnFailure:
				self._removeHostFromBackend(hostObj)

			if self._sshConnection is not None:
				try:
					self._sshConnection.close()
				except Exception as error:
					logger.debug2("Closing SSH connection failed: %s", error)
		finally:
			try:
				self._executeViaSSH(f"rm -rf {remoteFolder}")
			except (Exception, paramiko.SSHException) as error:
				logger.error(error)

	def _getHostId(self, host):
		hostId = None
		try:
			hostId = super()._getHostId(host)
		except socket.herror as error:
			logger.warning("Resolving hostName failed, attempting to resolve fqdn via ssh connection to ip")
			if re.match(r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}', host):
				ssh = paramiko.SSHClient()
				ssh.set_missing_host_key_policy(self._sshPolicy())
				ssh.connect(host, "22", self.username, self.password)
				stdin, stdout, stderr = ssh.exec_command("hostname -f")
				hostId = stdout.readlines()[0].encode('ascii','ignore').strip()
				logger.info("resolved FQDN: %s (type %s)", hostId, type(hostId))
		if hostId:
			return hostId
		raise ValueError(f"invalid host {host}")

	def _executeViaSSH(self, command):
		"""
		Executing a command via SSH.

		Will return the output of stdout and stderr in one iterable object.
		:raises SSHRemoteExecutionException: if exit code is not 0.
		"""
		self._connectViaSSH()

		logger.debug("Executing on remote: %s", command)

		with closing(self._sshConnection.get_transport().open_session()) as channel:
			channel.set_combine_stderr(True)
			channel.settimeout(None)  # blocking until completion of command

			channel.exec_command(command)
			exitCode = channel.recv_exit_status()
			out = channel.makefile("rb", -1).read().decode("utf-8", "replace")

			logger.debug("Exit code was: %s", exitCode)

			if exitCode:
				logger.debug("Command output: ")
				logger.debug(out)
				raise SSHRemoteExecutionException(
					f"Executing {command} on remote client failed! Got exit code {exitCode}"
				)

			return out

	def _getTargetArchitecture(self):
		logger.debug("Checking architecture of client...")
		output = self._executeViaSSH('uname -m')
		if "64" not in output:
			return "32"
		else:
			return "64"

	def _connectViaSSH(self):
		if self._sshConnection is not None:
			return

		self._sshConnection = paramiko.SSHClient()
		self._sshConnection.load_system_host_keys()
		self._sshConnection.set_missing_host_key_policy(self._sshPolicy())

		logger.debug("Connecting via SSH...")
		self._sshConnection.connect(
			hostname=self.networkAddress,
			username=self.username,
			password=self.password
		)

	def _copyFileOverSSH(self, localPath, remotePath):
		self._connectViaSSH()

		with closing(self._sshConnection.open_sftp()) as ftpConnection:
			ftpConnection.put(localPath, remotePath)

	def _copyDirectoryOverSSH(self, localPath, remotePath):
		@contextmanager
		def changeDirectory(path):
			currentDir = os.getcwd()
			os.chdir(path)
			yield
			os.chdir(currentDir)

		def createFolderIfMissing(path):
			try:
				ftpConnection.mkdir(path)
			except Exception as error:
				logger.debug("Can't create %s on remote: %s", path, error)

		self._connectViaSSH()

		with closing(self._sshConnection.open_sftp()) as ftpConnection:
			createFolderIfMissing(remotePath)

			if not os.path.exists(localPath):
				raise ValueError(f"Can't find local path '{localPath}'")

			# The following stunt is necessary to get results in 'dirpath'
			# that can be easily used for folder creation on the remote.
			with changeDirectory(os.path.join(localPath, '..')):
				directoryToWalk = os.path.basename(localPath)
				for dirpath, _, filenames in os.walk(directoryToWalk):
					createFolderIfMissing(os.path.join(remotePath, dirpath))

					for filename in filenames:
						local = os.path.join(dirpath, filename)
						remote = os.path.join(remotePath, dirpath, filename)

						logger.debug2("Copying %s -> %s", local, remote)
						ftpConnection.put(local, remote)

	def _finaliseInstallation(self, credentialsfile=None):
		if self.reboot:
			logger.notice("Rebooting machine %s", self.networkAddress)
			command = "shutdown -r 1 & disown"
			try:
				self._executeViaSSH(command)
			except Exception as error:
				logger.error("Failed to reboot computer: %s", error)
		elif self.shutdown:
			logger.notice("Shutting down machine %s", self.networkAddress)
			command = "shutdown -h 1 & disown"
			try:
				self._executeViaSSH(command)
			except Exception as error:
				logger.error("Failed to shutdown computer: %s", error)
		elif self.startService:
			logger.notice("Restarting opsiclientd service on computer: %s", self.networkAddress)
			command = "service opsiclientd restart"
			if credentialsfile:
				command = f"sudo --stdin -- {command} < {credentialsfile}"
			try:
				self._executeViaSSH(command)
			except Exception as error:
				logger.error("Failed to restart service opsiclientd on computer: %s", self.networkAddress)

	def _setOpsiClientAgentToInstalled(self, hostId):
		poc = ProductOnClient(
			productType='LocalbootProduct',
			clientId=hostId,
			productId='opsi-linux-client-agent',
			installationStatus='installed',
			actionResult='successful'
		)
		self.backend.productOnClient_updateObjects([poc])