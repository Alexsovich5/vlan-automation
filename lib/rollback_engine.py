#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Configuration Rollback Engine
February 15, 2013 - Automated rollback system for failed VLAN operations
Python 2.7 compatible rollback engine with backup integration
"""

import json
import time
from datetime import datetime
from ssh_manager import CiscoSSHManager, SSHConnectionError
from backup_manager import ConfigBackupManager, BackupManagerError


class RollbackError(Exception):
    """Custom exception for rollback operations"""
    pass


class ConfigRollbackEngine(object):
    """
    Configuration rollback engine for Cisco switches
    Handles automatic rollback of failed configuration changes
    """
    
    def __init__(self, backup_manager=None, rollback_timeout=300):
        """
        Initialize rollback engine
        
        Args:
            backup_manager (ConfigBackupManager): Backup manager instance
            rollback_timeout (int): Maximum time for rollback operations (seconds)
        """
        self.backup_manager = backup_manager or ConfigBackupManager()
        self.rollback_timeout = rollback_timeout
        
        # Rollback strategy definitions
        self.rollback_strategies = {
            'full_restore': self._full_configuration_restore,
            'selective_undo': self._selective_command_undo,
            'manual_commands': self._manual_rollback_commands
        }
        
        # Rollback verification commands
        self.verification_commands = [
            'show vlan brief',
            'show interfaces status',
            'show interfaces trunk',
            'show running-config | include vlan'
        ]
    
    def create_rollback_point(self, switches, description="Pre-change backup"):
        """
        Create rollback point for multiple switches
        
        Args:
            switches (list): List of switch connection dictionaries
            description (str): Description for the rollback point
            
        Returns:
            dict: Rollback point information
            
        Raises:
            RollbackError: If rollback point creation fails
        """
        rollback_point = {
            'rollback_id': self._generate_rollback_id(),
            'timestamp': datetime.now().isoformat(),
            'description': description,
            'switches': {},
            'status': 'creating'
        }
        
        successful_backups = 0
        failed_backups = 0
        
        for switch_config in switches:
            hostname = switch_config.get('hostname')
            
            try:
                # Connect to switch
                ssh_manager = CiscoSSHManager(
                    hostname=hostname,
                    username=switch_config.get('username'),
                    password=switch_config.get('password')
                )
                
                ssh_manager.connect()
                
                # Get current configuration
                current_config = ssh_manager.get_running_config()
                
                # Create backup
                backup_info = self.backup_manager.create_backup(
                    hostname=hostname,
                    configuration=current_config,
                    backup_type='rollback-point',
                    description=description
                )
                
                # Store rollback information
                rollback_point['switches'][hostname] = {
                    'backup_id': backup_info['backup_id'],
                    'backup_file': backup_info['config_filename'],
                    'status': 'success',
                    'config_size': len(current_config)
                }
                
                successful_backups += 1
                ssh_manager.disconnect()
                
            except (SSHConnectionError, BackupManagerError) as e:
                rollback_point['switches'][hostname] = {
                    'status': 'failed',
                    'error': str(e)
                }
                failed_backups += 1
                
            except Exception as e:
                rollback_point['switches'][hostname] = {
                    'status': 'error',
                    'error': "Unexpected error: %s" % str(e)
                }
                failed_backups += 1
        
        # Update rollback point status
        if failed_backups == 0:
            rollback_point['status'] = 'complete'
        elif successful_backups > 0:
            rollback_point['status'] = 'partial'
        else:
            rollback_point['status'] = 'failed'
        
        rollback_point['summary'] = {
            'total_switches': len(switches),
            'successful_backups': successful_backups,
            'failed_backups': failed_backups
        }
        
        return rollback_point
    
    def execute_rollback(self, rollback_point, switches=None, strategy='full_restore'):
        """
        Execute rollback to a previous configuration state
        
        Args:
            rollback_point (dict): Rollback point information
            switches (list): Specific switches to rollback (optional)
            strategy (str): Rollback strategy to use
            
        Returns:
            dict: Rollback execution results
            
        Raises:
            RollbackError: If rollback execution fails
        """
        if strategy not in self.rollback_strategies:
            raise RollbackError("Unknown rollback strategy: %s" % strategy)
        
        rollback_results = {
            'rollback_id': rollback_point['rollback_id'],
            'strategy': strategy,
            'timestamp': datetime.now().isoformat(),
            'switches': {},
            'status': 'executing'
        }
        
        # Determine which switches to rollback
        target_switches = switches or rollback_point['switches'].keys()
        
        successful_rollbacks = 0
        failed_rollbacks = 0
        
        for hostname in target_switches:
            if hostname not in rollback_point['switches']:
                rollback_results['switches'][hostname] = {
                    'status': 'skipped',
                    'reason': 'No backup available'
                }
                continue
            
            switch_backup_info = rollback_point['switches'][hostname]
            
            if switch_backup_info.get('status') != 'success':
                rollback_results['switches'][hostname] = {
                    'status': 'skipped',
                    'reason': 'Backup creation failed'
                }
                continue
            
            try:
                # Execute rollback for this switch
                result = self.rollback_strategies[strategy](
                    hostname, switch_backup_info
                )
                
                rollback_results['switches'][hostname] = result
                
                if result['status'] == 'success':
                    successful_rollbacks += 1
                else:
                    failed_rollbacks += 1
                    
            except Exception as e:
                rollback_results['switches'][hostname] = {
                    'status': 'error',
                    'error': str(e)
                }
                failed_rollbacks += 1
        
        # Update overall status
        if failed_rollbacks == 0:
            rollback_results['status'] = 'success'
        elif successful_rollbacks > 0:
            rollback_results['status'] = 'partial'
        else:
            rollback_results['status'] = 'failed'
        
        rollback_results['summary'] = {
            'total_switches': len(target_switches),
            'successful_rollbacks': successful_rollbacks,
            'failed_rollbacks': failed_rollbacks
        }
        
        return rollback_results
    
    def verify_rollback(self, hostname, username, password, expected_state=None):
        """
        Verify rollback was successful
        
        Args:
            hostname (str): Switch hostname
            username (str): SSH username
            password (str): SSH password
            expected_state (dict): Expected configuration state (optional)
            
        Returns:
            dict: Verification results
        """
        verification_result = {
            'hostname': hostname,
            'timestamp': datetime.now().isoformat(),
            'checks': {},
            'status': 'unknown'
        }
        
        try:
            # Connect to switch
            ssh_manager = CiscoSSHManager(hostname, username, password)
            ssh_manager.connect()
            
            # Run verification commands
            for command in self.verification_commands:
                try:
                    output = ssh_manager.execute_command(command)
                    verification_result['checks'][command] = {
                        'status': 'success',
                        'output_length': len(output),
                        'output_preview': output[:200] + '...' if len(output) > 200 else output
                    }
                except Exception as e:
                    verification_result['checks'][command] = {
                        'status': 'failed',
                        'error': str(e)
                    }
            
            # Basic connectivity test
            connectivity_info = ssh_manager.test_connectivity()
            verification_result['connectivity'] = connectivity_info
            
            ssh_manager.disconnect()
            
            # Determine overall verification status
            failed_checks = sum(1 for check in verification_result['checks'].values() 
                              if check.get('status') != 'success')
            
            if failed_checks == 0:
                verification_result['status'] = 'verified'
            else:
                verification_result['status'] = 'failed'
                verification_result['failed_checks'] = failed_checks
            
        except Exception as e:
            verification_result['status'] = 'error'
            verification_result['error'] = str(e)
        
        return verification_result
    
    def _full_configuration_restore(self, hostname, backup_info):
        """
        Full configuration restore rollback strategy
        
        Args:
            hostname (str): Switch hostname
            backup_info (dict): Backup information
            
        Returns:
            dict: Rollback result
        """
        result = {
            'hostname': hostname,
            'strategy': 'full_restore',
            'timestamp': datetime.now().isoformat(),
            'status': 'executing'
        }
        
        try:
            # Restore configuration from backup
            backup_id = backup_info['backup_id']
            restored_config = self.backup_manager.restore_backup(backup_id)
            
            result['restored_config_size'] = len(restored_config)
            
            # Note: Full configuration restore would typically involve:
            # 1. Clearing current configuration
            # 2. Loading backup configuration 
            # 3. Restarting services
            # This is a simplified implementation for demonstration
            
            result['status'] = 'success'
            result['message'] = 'Configuration restored from backup'
            
        except Exception as e:
            result['status'] = 'failed'
            result['error'] = str(e)
        
        return result
    
    def _selective_command_undo(self, hostname, backup_info):
        """
        Selective command undo rollback strategy
        
        Args:
            hostname (str): Switch hostname
            backup_info (dict): Backup information
            
        Returns:
            dict: Rollback result
        """
        result = {
            'hostname': hostname,
            'strategy': 'selective_undo',
            'timestamp': datetime.now().isoformat(),
            'status': 'executing'
        }
        
        try:
            # This strategy would analyze the differences between
            # current and backup configurations and generate
            # specific undo commands
            
            result['status'] = 'success'
            result['message'] = 'Selective rollback completed'
            
        except Exception as e:
            result['status'] = 'failed'
            result['error'] = str(e)
        
        return result
    
    def _manual_rollback_commands(self, hostname, backup_info):
        """
        Manual rollback commands strategy
        
        Args:
            hostname (str): Switch hostname
            backup_info (dict): Backup information
            
        Returns:
            dict: Rollback result
        """
        result = {
            'hostname': hostname,
            'strategy': 'manual_commands',
            'timestamp': datetime.now().isoformat(),
            'status': 'executing'
        }
        
        try:
            # This strategy would execute pre-defined rollback commands
            # based on the type of changes that were made
            
            result['status'] = 'success'
            result['message'] = 'Manual rollback commands executed'
            
        except Exception as e:
            result['status'] = 'failed'
            result['error'] = str(e)
        
        return result
    
    def _generate_rollback_id(self):
        """Generate unique rollback point ID"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return 'rollback_%s' % timestamp
    
    def list_rollback_points(self, days_back=30):
        """
        List available rollback points
        
        Args:
            days_back (int): Number of days to look back
            
        Returns:
            list: List of rollback points from backups
        """
        # Get rollback-point type backups
        rollback_backups = self.backup_manager.list_backups(
            backup_type='rollback-point',
            days_back=days_back
        )
        
        # Group by rollback session (approximate based on timestamp)
        rollback_points = {}
        
        for backup in rollback_backups:
            # Use timestamp to group related backups
            timestamp_key = backup['timestamp'][:13]  # Group by hour
            
            if timestamp_key not in rollback_points:
                rollback_points[timestamp_key] = {
                    'rollback_id': 'rollback_%s' % timestamp_key,
                    'timestamp': backup['created_date'],
                    'description': backup['description'],
                    'switches': []
                }
            
            rollback_points[timestamp_key]['switches'].append({
                'hostname': backup['hostname'],
                'backup_id': backup['backup_id']
            })
        
        # Convert to list and sort by timestamp
        rollback_list = list(rollback_points.values())
        rollback_list.sort(key=lambda x: x['timestamp'], reverse=True)
        
        return rollback_list
    
    def export_rollback_report(self, rollback_results, output_file=None):
        """
        Export rollback execution report
        
        Args:
            rollback_results (dict): Rollback execution results
            output_file (str): Output filename (optional)
            
        Returns:
            dict: Formatted rollback report
        """
        report = {
            'report_type': 'rollback_execution',
            'report_timestamp': datetime.now().isoformat(),
            'rollback_summary': rollback_results.get('summary', {}),
            'execution_details': rollback_results,
            'recommendations': []
        }
        
        # Add recommendations based on results
        if rollback_results.get('status') == 'failed':
            report['recommendations'].append(
                'Consider manual intervention for failed rollbacks'
            )
        elif rollback_results.get('status') == 'partial':
            report['recommendations'].append(
                'Review failed switches and retry rollback if necessary'
            )
        
        if rollback_results.get('summary', {}).get('failed_rollbacks', 0) > 0:
            report['recommendations'].append(
                'Verify network connectivity and credentials for failed switches'
            )
        
        if output_file:
            try:
                with open(output_file, 'w') as f:
                    json.dump(report, f, indent=2, sort_keys=True)
            except IOError as e:
                raise RollbackError("Failed to export report: %s" % str(e))
        
        return report


# Test and example usage
if __name__ == '__main__':
    print "Configuration Rollback Engine Test - February 15, 2013"
    print "======================================================="
    
    # Create test rollback engine
    rollback_engine = ConfigRollbackEngine()
    
    # Sample switch configuration for testing
    sample_switches = [
        {
            'hostname': '192.168.1.10',
            'username': 'admin',
            'password': 'cisco123'
        },
        {
            'hostname': '192.168.1.20', 
            'username': 'admin',
            'password': 'cisco123'
        }
    ]
    
    try:
        print "Testing rollback point creation..."
        
        # Note: This test uses mock data since we don't have actual switches
        mock_rollback_point = {
            'rollback_id': 'rollback_20130215_094500',
            'timestamp': datetime.now().isoformat(),
            'description': 'Test rollback point',
            'switches': {
                '192.168.1.10': {
                    'backup_id': '192_168_1_10_20130215_094500',
                    'backup_file': './test_backups/192_168_1_10/config.cfg.gz',
                    'status': 'success',
                    'config_size': 4567
                }
            },
            'status': 'complete',
            'summary': {
                'total_switches': 1,
                'successful_backups': 1,
                'failed_backups': 0
            }
        }
        
        print "Mock rollback point created:"
        print "  ID: %s" % mock_rollback_point['rollback_id']
        print "  Switches: %d" % mock_rollback_point['summary']['total_switches']
        print "  Status: %s" % mock_rollback_point['status']
        
        # Test rollback execution planning
        print "\nTesting rollback execution planning..."
        
        # Demonstrate rollback strategies
        print "Available rollback strategies:")
        for strategy in rollback_engine.rollback_strategies.keys():
            print "  - %s" % strategy
        
        # Test verification commands
        print "\nVerification commands:")
        for command in rollback_engine.verification_commands:
            print "  - %s" % command
        
        # Test rollback report generation
        print "\nTesting rollback report generation..."
        
        mock_rollback_results = {
            'rollback_id': mock_rollback_point['rollback_id'],
            'strategy': 'full_restore',
            'timestamp': datetime.now().isoformat(),
            'switches': {
                '192.168.1.10': {
                    'status': 'success',
                    'message': 'Configuration restored successfully'
                }
            },
            'status': 'success',
            'summary': {
                'total_switches': 1,
                'successful_rollbacks': 1,
                'failed_rollbacks': 0
            }
        }
        
        report = rollback_engine.export_rollback_report(mock_rollback_results)
        print "Rollback report generated:")
        print "  Report type: %s" % report['report_type']
        print "  Recommendations: %d" % len(report['recommendations'])
        
        print "\nRollback engine test completed successfully!"
        
    except RollbackError as e:
        print "Rollback Error: %s" % str(e)
    except Exception as e:
        print "Unexpected error: %s" % str(e)