#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
SSH Connection Manager for Cisco Switch Access
January 15, 2013 - Paramiko-based SSH client for switch access
Python 2.7 compatible implementation for VLAN automation
"""

import paramiko
import socket
import time
import threading
from datetime import datetime


class SSHConnectionError(Exception):
    """Custom exception for SSH connection errors"""
    pass


class CiscoSSHManager(object):
    """
    SSH connection manager for Cisco switches
    Handles authentication, command execution, and session management
    """
    
    def __init__(self, hostname, username, password, port=22, timeout=30):
        """
        Initialize SSH connection manager
        
        Args:
            hostname (str): Switch IP address or hostname
            username (str): SSH username
            password (str): SSH password
            port (int): SSH port (default 22)
            timeout (int): Connection timeout in seconds
        """
        self.hostname = hostname
        self.username = username
        self.password = password
        self.port = port
        self.timeout = timeout
        
        self.client = None
        self.shell = None
        self.connected = False
        self.lock = threading.Lock()
        
        # Cisco switch prompt patterns (2013 era)
        self.prompt_patterns = [
            r'[\w\-]+\>\s*$',     # User mode prompt
            r'[\w\-]+\#\s*$',     # Privileged mode prompt
            r'[\w\-]+\(config\)\#\s*$',  # Config mode prompt
        ]
        
    def connect(self):
        """
        Establish SSH connection to Cisco switch
        
        Returns:
            bool: True if connection successful, False otherwise
            
        Raises:
            SSHConnectionError: If connection fails
        """
        try:
            # Create SSH client with 2013 Paramiko settings
            self.client = paramiko.SSHClient()
            self.client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
            
            # Connect to switch
            self.client.connect(
                hostname=self.hostname,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=self.timeout,
                allow_agent=False,
                look_for_keys=False
            )
            
            # Create interactive shell for Cisco IOS
            self.shell = self.client.invoke_shell()
            self.shell.settimeout(self.timeout)
            
            # Wait for initial prompt and clear any welcome messages
            time.sleep(1)
            self._clear_buffer()
            
            # Enter privileged mode if not already there
            if not self._is_privileged_mode():
                self._enter_privileged_mode()
            
            self.connected = True
            return True
            
        except paramiko.AuthenticationException:
            raise SSHConnectionError("Authentication failed for %s" % self.hostname)
        except paramiko.SSHException as e:
            raise SSHConnectionError("SSH connection error: %s" % str(e))
        except socket.error as e:
            raise SSHConnectionError("Network error connecting to %s: %s" % (self.hostname, str(e)))
        except Exception as e:
            raise SSHConnectionError("Unexpected error: %s" % str(e))
    
    def disconnect(self):
        """Close SSH connection"""
        with self.lock:
            if self.shell:
                self.shell.close()
                self.shell = None
            if self.client:
                self.client.close()
                self.client = None
            self.connected = False
    
    def execute_command(self, command, wait_time=2):
        """
        Execute command on Cisco switch
        
        Args:
            command (str): IOS command to execute
            wait_time (float): Time to wait for command completion
            
        Returns:
            str: Command output
            
        Raises:
            SSHConnectionError: If not connected or command fails
        """
        if not self.connected or not self.shell:
            raise SSHConnectionError("Not connected to switch")
        
        with self.lock:
            try:
                # Clear any existing output
                self._clear_buffer()
                
                # Send command
                self.shell.send(command + '\n')
                
                # Wait for command to complete
                time.sleep(wait_time)
                
                # Read output
                output = self._read_until_prompt()
                
                # Remove echo of the command and prompt
                lines = output.split('\n')
                if len(lines) > 0 and command.strip() in lines[0]:
                    lines = lines[1:]  # Remove command echo
                
                # Remove last line if it contains prompt
                if len(lines) > 0:
                    for pattern in self.prompt_patterns:
                        import re
                        if re.search(pattern, lines[-1]):
                            lines = lines[:-1]
                            break
                
                return '\n'.join(lines).strip()
                
            except socket.timeout:
                raise SSHConnectionError("Command timeout: %s" % command)
            except Exception as e:
                raise SSHConnectionError("Command execution error: %s" % str(e))
    
    def execute_config_commands(self, commands):
        """
        Execute configuration commands in config mode
        
        Args:
            commands (list): List of IOS configuration commands
            
        Returns:
            list: List of command outputs
            
        Raises:
            SSHConnectionError: If configuration fails
        """
        if not self.connected:
            raise SSHConnectionError("Not connected to switch")
        
        outputs = []
        
        try:
            # Enter configuration mode
            self.execute_command('configure terminal')
            
            # Execute each command
            for command in commands:
                if command.strip():  # Skip empty commands
                    output = self.execute_command(command.strip())
                    outputs.append(output)
            
            # Exit configuration mode
            self.execute_command('end')
            
            return outputs
            
        except Exception as e:
            # Try to exit config mode on error
            try:
                self.execute_command('end')
            except:
                pass
            raise SSHConnectionError("Configuration command failed: %s" % str(e))
    
    def get_running_config(self):
        """
        Get current running configuration
        
        Returns:
            str: Running configuration
        """
        return self.execute_command('show running-config', wait_time=5)
    
    def get_vlan_config(self):
        """
        Get VLAN configuration
        
        Returns:
            str: VLAN configuration output
        """
        return self.execute_command('show vlan brief')
    
    def save_config(self):
        """
        Save running configuration to startup configuration
        
        Returns:
            str: Save command output
        """
        # Use 'copy run start' and automatically confirm
        output = self.execute_command('copy running-config startup-config')
        
        # Handle confirmation prompt if present
        if 'Destination filename' in output or '[startup-config]' in output:
            time.sleep(1)
            self.shell.send('\n')  # Confirm with enter
            time.sleep(2)
            additional_output = self._read_until_prompt()
            output += '\n' + additional_output
        
        return output
    
    def _clear_buffer(self):
        """Clear any pending output in the buffer"""
        try:
            while self.shell.recv_ready():
                self.shell.recv(4096)
        except:
            pass
    
    def _read_until_prompt(self, max_wait=30):
        """
        Read output until switch prompt is detected
        
        Args:
            max_wait (int): Maximum time to wait for prompt
            
        Returns:
            str: Output received
        """
        import re
        output = ''
        start_time = time.time()
        
        while time.time() - start_time < max_wait:
            if self.shell.recv_ready():
                data = self.shell.recv(4096)
                output += data
                
                # Check if we have a prompt
                lines = output.split('\n')
                if lines and lines[-1].strip():
                    last_line = lines[-1].strip()
                    for pattern in self.prompt_patterns:
                        if re.search(pattern, last_line):
                            return output
            
            time.sleep(0.1)
        
        return output
    
    def _is_privileged_mode(self):
        """Check if currently in privileged mode"""
        try:
            self._clear_buffer()
            self.shell.send('\n')
            time.sleep(0.5)
            output = self._read_until_prompt()
            return '#' in output.split('\n')[-1]
        except:
            return False
    
    def _enter_privileged_mode(self):
        """Enter privileged mode"""
        try:
            output = self.execute_command('enable')
            
            # Check if password is required
            if 'Password:' in output:
                # For many switches, enable password is same as login password
                self.shell.send(self.password + '\n')
                time.sleep(1)
                self._read_until_prompt()
            
            # Verify we're in privileged mode
            if not self._is_privileged_mode():
                raise SSHConnectionError("Failed to enter privileged mode")
                
        except Exception as e:
            raise SSHConnectionError("Could not enter privileged mode: %s" % str(e))
    
    def test_connectivity(self):
        """
        Test basic connectivity and gather switch information
        
        Returns:
            dict: Basic switch information
        """
        if not self.connected:
            raise SSHConnectionError("Not connected to switch")
        
        info = {
            'hostname': self.hostname,
            'connected': self.connected,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        }
        
        try:
            # Get switch version info
            version_output = self.execute_command('show version')
            
            # Parse basic information (simple parsing for 2013)
            lines = version_output.split('\n')
            for line in lines:
                line = line.strip()
                if 'Cisco IOS Software' in line:
                    info['ios_version'] = line
                elif 'uptime is' in line:
                    info['uptime'] = line
                elif 'System image file is' in line:
                    info['image_file'] = line
            
            # Get hostname
            hostname_output = self.execute_command('show running-config | include hostname')
            if hostname_output:
                for line in hostname_output.split('\n'):
                    if line.strip().startswith('hostname'):
                        info['switch_hostname'] = line.strip().split()[-1]
                        break
            
            info['status'] = 'success'
            
        except Exception as e:
            info['status'] = 'error'
            info['error'] = str(e)
        
        return info


# Test connectivity function for standalone testing
if __name__ == '__main__':
    import sys
    
    print "Cisco SSH Manager Test - January 15, 2013"
    print "=========================================="
    
    if len(sys.argv) < 4:
        print "Usage: python ssh_manager.py <hostname> <username> <password>"
        sys.exit(1)
    
    hostname = sys.argv[1]
    username = sys.argv[2]
    password = sys.argv[3]
    
    try:
        # Create connection
        ssh = CiscoSSHManager(hostname, username, password)
        
        print "Connecting to %s..." % hostname
        ssh.connect()
        print "Connected successfully!"
        
        # Test basic commands
        print "\nTesting connectivity..."
        info = ssh.test_connectivity()
        
        print "Switch Information:"
        for key, value in info.items():
            print "  %s: %s" % (key, value)
        
        # Test VLAN command
        print "\nGetting VLAN information..."
        vlan_output = ssh.get_vlan_config()
        print "VLAN Config (first 10 lines):"
        for line in vlan_output.split('\n')[:10]:
            print "  %s" % line
        
        print "\nDisconnecting..."
        ssh.disconnect()
        print "Test completed successfully!"
        
    except SSHConnectionError as e:
        print "SSH Error: %s" % str(e)
        sys.exit(1)
    except Exception as e:
        print "Unexpected error: %s" % str(e)
        sys.exit(1)