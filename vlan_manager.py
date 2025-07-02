#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Multi-Switch VLAN Manager
February 22, 2013 - Orchestrate VLAN operations across multiple switches
Python 2.7 compatible multi-switch automation with parallel execution
"""

import os
import sys
import json
import time
import threading
from datetime import datetime
from optparse import OptionParser

# Import project modules
from lib.ssh_manager import CiscoSSHManager, SSHConnectionError
from lib.vlan_parser import CiscoVLANParser, VLANParseError
from lib.config_builder import CiscoConfigBuilder, ConfigBuilderError
from lib.backup_manager import ConfigBackupManager, BackupManagerError
from lib.rollback_engine import ConfigRollbackEngine, RollbackError


class VLANManagerError(Exception):
    """Custom exception for VLAN manager operations"""
    pass


class MultiSwitchVLANManager(object):
    """
    Multi-switch VLAN configuration manager
    Orchestrates VLAN operations across multiple Cisco switches
    """
    
    def __init__(self, config_file=None, max_concurrent=5):
        """
        Initialize multi-switch VLAN manager
        
        Args:
            config_file (str): Configuration file path
            max_concurrent (int): Maximum concurrent switch operations
        """
        self.config_file = config_file
        self.max_concurrent = max_concurrent
        
        # Load configuration
        self.config = self._load_configuration()
        
        # Initialize components
        self.vlan_parser = CiscoVLANParser()
        self.config_builder = CiscoConfigBuilder()
        self.backup_manager = ConfigBackupManager(
            backup_directory=self.config.get('global_settings', {}).get('backup_directory', './backups')
        )
        self.rollback_engine = ConfigRollbackEngine(self.backup_manager)
        
        # Thread management
        self.thread_lock = threading.Lock()
        self.active_operations = {}
        
        # Operation results
        self.operation_results = {}
    
    def execute_vlan_operation(self, operation_type, vlan_config, switches=None):
        """
        Execute VLAN operation across multiple switches
        
        Args:
            operation_type (str): Type of operation ('create', 'delete', 'modify')
            vlan_config (dict): VLAN configuration data
            switches (list): Specific switches to target (optional)
            
        Returns:
            dict: Operation results for all switches
        """
        if operation_type not in ['create', 'delete', 'modify']:
            raise VLANManagerError("Invalid operation type: %s" % operation_type)
        
        # Determine target switches
        target_switches = switches or self.config.get('switches', [])
        
        if not target_switches:
            raise VLANManagerError("No switches configured for operation")
        
        # Create rollback point before operations
        print "Creating rollback point for %d switches..." % len(target_switches)
        rollback_point = self.rollback_engine.create_rollback_point(
            target_switches,
            description="Pre-%s operation backup" % operation_type
        )
        
        print "Rollback point created: %s" % rollback_point['rollback_id']
        
        # Initialize operation tracking
        operation_id = self._generate_operation_id()
        self.operation_results[operation_id] = {
            'operation_type': operation_type,
            'operation_id': operation_id,
            'rollback_point': rollback_point,
            'timestamp': datetime.now().isoformat(),
            'switches': {},
            'status': 'executing'
        }
        
        # Execute operations using thread pool
        if self.config.get('global_settings', {}).get('parallel_execution', True):
            self._execute_parallel_operations(operation_id, operation_type, vlan_config, target_switches)
        else:
            self._execute_sequential_operations(operation_id, operation_type, vlan_config, target_switches)
        
        # Finalize operation results
        results = self.operation_results[operation_id]
        
        # Determine overall status
        failed_switches = sum(1 for switch_result in results['switches'].values() 
                            if switch_result.get('status') != 'success')
        
        if failed_switches == 0:
            results['status'] = 'success'
        elif failed_switches < len(target_switches):
            results['status'] = 'partial'
        else:
            results['status'] = 'failed'
            
        results['summary'] = {
            'total_switches': len(target_switches),
            'successful_operations': len(target_switches) - failed_switches,
            'failed_operations': failed_switches
        }
        
        return results
    
    def _execute_parallel_operations(self, operation_id, operation_type, vlan_config, switches):
        """Execute operations in parallel using threads"""
        threads = []
        thread_semaphore = threading.Semaphore(self.max_concurrent)
        
        def worker_thread(switch_config):
            thread_semaphore.acquire()
            try:
                result = self._execute_switch_operation(operation_type, vlan_config, switch_config)
                
                with self.thread_lock:
                    self.operation_results[operation_id]['switches'][switch_config['hostname']] = result
                    
            finally:
                thread_semaphore.release()
        
        # Start threads for each switch
        for switch_config in switches:
            thread = threading.Thread(target=worker_thread, args=(switch_config,))
            thread.daemon = True
            thread.start()
            threads.append(thread)
        
        # Wait for all threads to complete
        for thread in threads:
            thread.join(timeout=300)  # 5 minute timeout per thread
    
    def _execute_sequential_operations(self, operation_id, operation_type, vlan_config, switches):
        """Execute operations sequentially"""
        for switch_config in switches:
            result = self._execute_switch_operation(operation_type, vlan_config, switch_config)
            self.operation_results[operation_id]['switches'][switch_config['hostname']] = result
    
    def _execute_switch_operation(self, operation_type, vlan_config, switch_config):
        """
        Execute VLAN operation on a single switch
        
        Args:
            operation_type (str): Operation type
            vlan_config (dict): VLAN configuration
            switch_config (dict): Switch connection configuration
            
        Returns:
            dict: Operation result for the switch
        """
        hostname = switch_config['hostname']
        result = {
            'hostname': hostname,
            'operation_type': operation_type,
            'timestamp': datetime.now().isoformat(),
            'status': 'executing'
        }
        
        try:
            # Connect to switch
            ssh_manager = CiscoSSHManager(
                hostname=hostname,
                username=switch_config.get('username'),
                password=switch_config.get('password'),
                timeout=self.config.get('global_settings', {}).get('ssh_timeout', 30)
            )
            
            print "Connecting to %s..." % hostname
            ssh_manager.connect()
            
            # Get current VLAN configuration for validation
            current_vlan_output = ssh_manager.get_vlan_config()
            current_vlans = self.vlan_parser.parse_vlan_brief(current_vlan_output)
            
            # Build configuration commands based on operation type
            if operation_type == 'create':
                commands = self._build_create_commands(vlan_config, current_vlans)
            elif operation_type == 'delete':
                commands = self._build_delete_commands(vlan_config, current_vlans)
            elif operation_type == 'modify':
                commands = self._build_modify_commands(vlan_config, current_vlans)
            else:
                raise VLANManagerError("Unknown operation type: %s" % operation_type)
            
            result['commands_generated'] = len(commands)
            
            if not commands:
                result['status'] = 'skipped'
                result['message'] = 'No commands to execute'
                ssh_manager.disconnect()
                return result
            
            # Execute configuration commands
            print "Executing %d commands on %s..." % (len(commands), hostname)
            command_outputs = ssh_manager.execute_config_commands(commands)
            
            # Save configuration
            print "Saving configuration on %s..." % hostname
            save_output = ssh_manager.save_config()
            
            # Verify changes
            verification_output = ssh_manager.get_vlan_config()
            updated_vlans = self.vlan_parser.parse_vlan_brief(verification_output)
            
            result['commands_executed'] = len(command_outputs)
            result['vlans_before'] = len(current_vlans)
            result['vlans_after'] = len(updated_vlans)
            result['status'] = 'success'
            result['message'] = 'Operation completed successfully'
            
            ssh_manager.disconnect()
            
        except (SSHConnectionError, VLANParseError, ConfigBuilderError) as e:
            result['status'] = 'failed'
            result['error'] = str(e)
            
        except Exception as e:
            result['status'] = 'error'
            result['error'] = "Unexpected error: %s" % str(e)
        
        return result
    
    def _build_create_commands(self, vlan_config, current_vlans):
        """Build commands for VLAN creation"""
        commands = []
        
        # Get current VLAN IDs
        current_vlan_ids = set(vlan['id'] for vlan in current_vlans)
        
        # Build VLAN creation commands
        config_commands = self.config_builder.build_complete_config(vlan_config)
        
        # Filter out VLANs that already exist
        for command in config_commands.get('vlans', []):
            if 'vlan ' in command and not command.startswith('no vlan'):
                try:
                    vlan_id = int(command.split()[1])
                    if vlan_id not in current_vlan_ids:
                        commands.append(command)
                    else:
                        print "  VLAN %d already exists, skipping..." % vlan_id
                except (ValueError, IndexError):
                    commands.append(command)  # Add non-parseable commands anyway
            else:
                commands.append(command)
        
        # Add interface and trunk commands
        commands.extend(config_commands.get('interfaces', []))
        commands.extend(config_commands.get('trunks', []))
        
        return commands
    
    def _build_delete_commands(self, vlan_config, current_vlans):
        """Build commands for VLAN deletion"""
        vlan_ids = vlan_config.get('vlan_ids', [])
        return self.config_builder.delete_vlan_commands(vlan_ids)
    
    def _build_modify_commands(self, vlan_config, current_vlans):
        """Build commands for VLAN modification"""
        # For modification, we treat it as a create operation
        # but with additional validation
        return self._build_create_commands(vlan_config, current_vlans)
    
    def get_switch_inventory(self):
        """
        Get inventory of all configured switches
        
        Returns:
            dict: Switch inventory with connectivity status
        """
        inventory = {
            'total_switches': 0,
            'online_switches': 0,
            'offline_switches': 0,
            'switches': {}
        }
        
        switches = self.config.get('switches', [])
        inventory['total_switches'] = len(switches)
        
        for switch_config in switches:
            hostname = switch_config['hostname']
            
            try:
                ssh_manager = CiscoSSHManager(
                    hostname=hostname,
                    username=switch_config.get('username'),
                    password=switch_config.get('password'),
                    timeout=10  # Short timeout for inventory
                )
                
                ssh_manager.connect()
                connectivity_info = ssh_manager.test_connectivity()
                ssh_manager.disconnect()
                
                inventory['switches'][hostname] = {
                    'status': 'online',
                    'device_type': switch_config.get('device_type', 'unknown'),
                    'location': switch_config.get('location', 'unknown'),
                    'last_check': datetime.now().isoformat(),
                    'connectivity_info': connectivity_info
                }
                
                inventory['online_switches'] += 1
                
            except Exception as e:
                inventory['switches'][hostname] = {
                    'status': 'offline',
                    'device_type': switch_config.get('device_type', 'unknown'), 
                    'location': switch_config.get('location', 'unknown'),
                    'last_check': datetime.now().isoformat(),
                    'error': str(e)
                }
                
                inventory['offline_switches'] += 1
        
        return inventory
    
    def _load_configuration(self):
        """Load configuration from file"""
        if not self.config_file or not os.path.exists(self.config_file):
            return {
                'switches': [],
                'global_settings': {
                    'ssh_timeout': 30,
                    'parallel_execution': True,
                    'max_concurrent_connections': 5
                }
            }
        
        try:
            with open(self.config_file, 'r') as f:
                return json.load(f)
        except (IOError, ValueError) as e:
            raise VLANManagerError("Failed to load configuration: %s" % str(e))
    
    def _generate_operation_id(self):
        """Generate unique operation ID"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return 'op_%s' % timestamp


def main():
    """Main command-line interface"""
    parser = OptionParser(usage="usage: %prog [options]", 
                         version="VLAN Manager 1.0 - February 22, 2013")
    
    parser.add_option('-c', '--config', dest='config_file', 
                     default='config/switches.json',
                     help='Switch configuration file (default: config/switches.json)')
    
    parser.add_option('-v', '--vlans', dest='vlan_file',
                     help='VLAN configuration file')
    
    parser.add_option('-a', '--action', dest='action',
                     choices=['create', 'delete', 'modify', 'inventory'],
                     help='Action to perform (create, delete, modify, inventory)')
    
    parser.add_option('-s', '--switches', dest='switches',
                     help='Comma-separated list of switch hostnames (optional)')
    
    parser.add_option('--parallel', dest='parallel', action='store_true',
                     default=True, help='Enable parallel execution (default)')
    
    parser.add_option('--sequential', dest='parallel', action='store_false',
                     help='Use sequential execution')
    
    (options, args) = parser.parse_args()
    
    if not options.action:
        parser.error("Action is required. Use --help for options.")
    
    try:
        # Initialize VLAN manager
        vlan_manager = MultiSwitchVLANManager(
            config_file=options.config_file,
            max_concurrent=5
        )
        
        if options.action == 'inventory':
            print "Getting switch inventory..."
            inventory = vlan_manager.get_switch_inventory()
            
            print "\nSwitch Inventory Report"
            print "======================="
            print "Total switches: %d" % inventory['total_switches']
            print "Online switches: %d" % inventory['online_switches']
            print "Offline switches: %d" % inventory['offline_switches']
            
            print "\nSwitch Details:"
            for hostname, info in inventory['switches'].items():
                print "  %s - %s (%s)" % (hostname, info['status'], info['device_type'])
                if info['status'] == 'offline':
                    print "    Error: %s" % info.get('error', 'Unknown')
        
        else:
            if not options.vlan_file:
                parser.error("VLAN configuration file is required for %s action" % options.action)
            
            # Load VLAN configuration
            try:
                with open(options.vlan_file, 'r') as f:
                    vlan_config = json.load(f)
            except (IOError, ValueError) as e:
                print "Error loading VLAN configuration: %s" % str(e)
                sys.exit(1)
            
            # Parse target switches
            target_switches = None
            if options.switches:
                switch_hostnames = [s.strip() for s in options.switches.split(',')]
                # Filter configured switches
                all_switches = vlan_manager.config.get('switches', [])
                target_switches = [s for s in all_switches 
                                 if s['hostname'] in switch_hostnames]
            
            # Execute operation
            print "Executing %s operation..." % options.action
            results = vlan_manager.execute_vlan_operation(
                options.action,
                vlan_config,
                target_switches
            )
            
            # Display results
            print "\nOperation Results"
            print "================"
            print "Operation ID: %s" % results['operation_id']
            print "Status: %s" % results['status']
            print "Total switches: %d" % results['summary']['total_switches']
            print "Successful: %d" % results['summary']['successful_operations']
            print "Failed: %d" % results['summary']['failed_operations']
            
            print "\nSwitch Details:"
            for hostname, switch_result in results['switches'].items():
                print "  %s - %s" % (hostname, switch_result['status'])
                if switch_result['status'] != 'success':
                    print "    Error: %s" % switch_result.get('error', 'Unknown error')
                else:
                    print "    Commands: %d" % switch_result.get('commands_executed', 0)
    
    except VLANManagerError as e:
        print "VLAN Manager Error: %s" % str(e)
        sys.exit(1)
    except KeyboardInterrupt:
        print "\nOperation cancelled by user"
        sys.exit(1)
    except Exception as e:
        print "Unexpected error: %s" % str(e)
        sys.exit(1)


if __name__ == '__main__':
    main()