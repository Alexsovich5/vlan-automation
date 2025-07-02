#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
VLAN Automation Logging System
March 8, 2013 - Comprehensive audit logging and event tracking
Python 2.7 compatible logging system for compliance and troubleshooting
"""

import os
import sys
import json
import time
import logging
import logging.handlers
from datetime import datetime
import threading


class VLANAuditLogger(object):
    """
    Comprehensive audit logging system for VLAN automation
    Provides structured logging with multiple output formats and rotation
    """
    
    def __init__(self, log_directory='./logs', log_level='INFO', max_log_size=10485760, backup_count=5):
        """
        Initialize audit logging system
        
        Args:
            log_directory (str): Directory for log files
            log_level (str): Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            max_log_size (int): Maximum log file size in bytes (default 10MB)
            backup_count (int): Number of backup log files to keep
        """
        self.log_directory = log_directory
        self.log_level = getattr(logging, log_level.upper(), logging.INFO)
        self.max_log_size = max_log_size
        self.backup_count = backup_count
        
        # Ensure log directory exists
        if not os.path.exists(self.log_directory):
            try:
                os.makedirs(self.log_directory)
            except OSError as e:
                print "Warning: Could not create log directory: %s" % str(e)
                self.log_directory = '.'
        
        # Initialize loggers
        self._setup_loggers()
        
        # Thread lock for thread-safe logging
        self.log_lock = threading.Lock()
        
        # Log session information
        self.session_id = self._generate_session_id()
        self.start_time = datetime.now()
        
        # Event counters
        self.event_counters = {
            'operations': 0,
            'successes': 0,
            'failures': 0,
            'warnings': 0,
            'connections': 0
        }
    
    def _setup_loggers(self):
        """Setup different logger instances for various log types"""
        
        # Main application logger
        self.app_logger = self._create_logger(
            'vlan_automation',
            os.path.join(self.log_directory, 'vlan_automation.log'),
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # Audit logger for compliance tracking
        self.audit_logger = self._create_logger(
            'vlan_audit',
            os.path.join(self.log_directory, 'vlan_audit.log'),
            '%(asctime)s - AUDIT - %(message)s',
            level=logging.INFO  # Audit logs are always INFO or higher
        )
        
        # Operations logger for detailed operation tracking
        self.ops_logger = self._create_logger(
            'vlan_operations',
            os.path.join(self.log_directory, 'vlan_operations.log'),
            '%(asctime)s - %(levelname)s - %(message)s'
        )
        
        # Error logger for error analysis
        self.error_logger = self._create_logger(
            'vlan_errors',
            os.path.join(self.log_directory, 'vlan_errors.log'),
            '%(asctime)s - ERROR - %(message)s',
            level=logging.ERROR
        )
        
        # Console logger for real-time feedback
        self.console_logger = self._create_console_logger()
    
    def _create_logger(self, name, filename, format_string, level=None):
        """Create a logger with rotating file handler"""
        logger = logging.getLogger(name)
        logger.setLevel(level or self.log_level)
        
        # Remove existing handlers to avoid duplicates
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        # Create rotating file handler
        handler = logging.handlers.RotatingFileHandler(
            filename,
            maxBytes=self.max_log_size,
            backupCount=self.backup_count
        )
        
        # Set formatter
        formatter = logging.Formatter(format_string)
        handler.setFormatter(formatter)
        
        logger.addHandler(handler)
        return logger
    
    def _create_console_logger(self):
        """Create console logger for real-time output"""
        logger = logging.getLogger('vlan_console')
        logger.setLevel(self.log_level)
        
        # Remove existing handlers
        for handler in logger.handlers[:]:
            logger.removeHandler(handler)
        
        # Create console handler
        handler = logging.StreamHandler(sys.stdout)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        
        logger.addHandler(handler)
        return logger
    
    def log_operation_start(self, operation_type, switches, user=None, config_summary=None):
        """
        Log the start of a VLAN operation
        
        Args:
            operation_type (str): Type of operation (create, delete, modify)
            switches (list): List of target switches
            user (str): Username performing operation
            config_summary (dict): Summary of configuration changes
        """
        with self.log_lock:
            self.event_counters['operations'] += 1
            
            log_entry = {
                'event_type': 'operation_start',
                'session_id': self.session_id,
                'operation_type': operation_type,
                'timestamp': datetime.now().isoformat(),
                'user': user or 'unknown',
                'target_switches': [s.get('hostname', 'unknown') for s in switches],
                'switch_count': len(switches),
                'config_summary': config_summary
            }
            
            # Log to multiple loggers
            message = "Operation started: %s on %d switches" % (operation_type, len(switches))
            
            self.app_logger.info(message)
            self.ops_logger.info(json.dumps(log_entry))
            self.audit_logger.info("USER=%s ACTION=START OPERATION=%s SWITCHES=%d" % (
                user or 'unknown', operation_type, len(switches)
            ))
            self.console_logger.info(message)
    
    def log_operation_complete(self, operation_type, results, duration=None):
        """
        Log the completion of a VLAN operation
        
        Args:
            operation_type (str): Type of operation
            results (dict): Operation results
            duration (float): Operation duration in seconds
        """
        with self.log_lock:
            status = results.get('status', 'unknown')
            
            if status == 'success':
                self.event_counters['successes'] += 1
            else:
                self.event_counters['failures'] += 1
            
            log_entry = {
                'event_type': 'operation_complete',
                'session_id': self.session_id,
                'operation_type': operation_type,
                'timestamp': datetime.now().isoformat(),
                'status': status,
                'duration_seconds': duration,
                'summary': results.get('summary', {}),
                'operation_id': results.get('operation_id')
            }
            
            message = "Operation completed: %s - Status: %s" % (operation_type, status)
            if duration:
                message += " (Duration: %.2fs)" % duration
            
            self.app_logger.info(message)
            self.ops_logger.info(json.dumps(log_entry))
            self.audit_logger.info("ACTION=COMPLETE OPERATION=%s STATUS=%s DURATION=%.2fs" % (
                operation_type, status, duration or 0
            ))
            
            if status == 'success':
                self.console_logger.info(message)
            else:
                self.console_logger.error(message)
    
    def log_switch_connection(self, hostname, status, error=None, connection_time=None):
        """
        Log switch connection attempts
        
        Args:
            hostname (str): Switch hostname/IP
            status (str): Connection status (success, failed, timeout)
            error (str): Error message if connection failed
            connection_time (float): Time to establish connection
        """
        with self.log_lock:
            self.event_counters['connections'] += 1
            
            log_entry = {
                'event_type': 'switch_connection',
                'session_id': self.session_id,
                'timestamp': datetime.now().isoformat(),
                'hostname': hostname,
                'status': status,
                'connection_time': connection_time,
                'error': error
            }
            
            message = "Switch connection: %s - Status: %s" % (hostname, status)
            
            if status == 'success':
                self.app_logger.info(message)
                self.console_logger.debug(message)
            else:
                self.app_logger.warning(message)
                self.console_logger.warning(message)
                if error:
                    self.error_logger.error("Connection failed to %s: %s" % (hostname, error))
            
            self.ops_logger.info(json.dumps(log_entry))
    
    def log_configuration_change(self, hostname, change_type, details, success=True):
        """
        Log individual configuration changes
        
        Args:
            hostname (str): Switch hostname
            change_type (str): Type of change (vlan_create, interface_config, etc.)
            details (dict): Change details
            success (bool): Whether change was successful
        """
        with self.log_lock:
            log_entry = {
                'event_type': 'configuration_change',
                'session_id': self.session_id,
                'timestamp': datetime.now().isoformat(),
                'hostname': hostname,
                'change_type': change_type,
                'success': success,
                'details': details
            }
            
            message = "Config change on %s: %s - %s" % (
                hostname, change_type, 'SUCCESS' if success else 'FAILED'
            )
            
            if success:
                self.app_logger.info(message)
            else:
                self.app_logger.error(message)
                self.error_logger.error(json.dumps(log_entry))
            
            self.ops_logger.info(json.dumps(log_entry))
            self.audit_logger.info("HOST=%s CHANGE=%s STATUS=%s" % (
                hostname, change_type, 'SUCCESS' if success else 'FAILED'
            ))
    
    def log_backup_operation(self, hostname, backup_type, backup_id, success=True, error=None):
        """
        Log backup operations
        
        Args:
            hostname (str): Switch hostname
            backup_type (str): Type of backup (pre-change, manual, etc.)
            backup_id (str): Backup identifier
            success (bool): Whether backup was successful
            error (str): Error message if backup failed
        """
        with self.log_lock:
            log_entry = {
                'event_type': 'backup_operation',
                'session_id': self.session_id,
                'timestamp': datetime.now().isoformat(),
                'hostname': hostname,
                'backup_type': backup_type,
                'backup_id': backup_id,
                'success': success,
                'error': error
            }
            
            message = "Backup operation: %s on %s - %s" % (
                backup_type, hostname, 'SUCCESS' if success else 'FAILED'
            )
            
            if success:
                self.app_logger.info(message)
            else:
                self.app_logger.error(message)
                if error:
                    self.error_logger.error("Backup failed for %s: %s" % (hostname, error))
            
            self.ops_logger.info(json.dumps(log_entry))
            self.audit_logger.info("HOST=%s BACKUP=%s ID=%s STATUS=%s" % (
                hostname, backup_type, backup_id, 'SUCCESS' if success else 'FAILED'
            ))
    
    def log_rollback_operation(self, operation_id, switches, success=True, details=None):
        """
        Log rollback operations
        
        Args:
            operation_id (str): Original operation ID being rolled back
            switches (list): List of switches involved in rollback
            success (bool): Whether rollback was successful
            details (dict): Rollback details
        """
        with self.log_lock:
            log_entry = {
                'event_type': 'rollback_operation',
                'session_id': self.session_id,
                'timestamp': datetime.now().isoformat(),
                'original_operation_id': operation_id,
                'switches': switches,
                'success': success,
                'details': details
            }
            
            message = "Rollback operation for %s: %d switches - %s" % (
                operation_id, len(switches), 'SUCCESS' if success else 'FAILED'
            )
            
            if success:
                self.app_logger.info(message)
                self.console_logger.info(message)
            else:
                self.app_logger.error(message)
                self.console_logger.error(message)
                self.error_logger.error(json.dumps(log_entry))
            
            self.ops_logger.info(json.dumps(log_entry))
            self.audit_logger.info("ACTION=ROLLBACK OPERATION=%s SWITCHES=%d STATUS=%s" % (
                operation_id, len(switches), 'SUCCESS' if success else 'FAILED'
            ))
    
    def log_validation_results(self, config_file, validation_status, issue_count, critical_issues):
        """
        Log configuration validation results
        
        Args:
            config_file (str): Configuration file validated
            validation_status (str): Overall validation status
            issue_count (int): Total number of issues found
            critical_issues (int): Number of critical issues
        """
        with self.log_lock:
            if critical_issues > 0:
                self.event_counters['warnings'] += 1
            
            log_entry = {
                'event_type': 'validation',
                'session_id': self.session_id,
                'timestamp': datetime.now().isoformat(),
                'config_file': config_file,
                'validation_status': validation_status,
                'total_issues': issue_count,
                'critical_issues': critical_issues
            }
            
            message = "Validation: %s - Status: %s (%d issues, %d critical)" % (
                config_file, validation_status, issue_count, critical_issues
            )
            
            if validation_status == 'passed':
                self.app_logger.info(message)
                self.console_logger.info(message)
            elif critical_issues > 0:
                self.app_logger.error(message)
                self.console_logger.error(message)
            else:
                self.app_logger.warning(message)
                self.console_logger.warning(message)
            
            self.ops_logger.info(json.dumps(log_entry))
    
    def log_error(self, error_type, error_message, context=None, hostname=None):
        """
        Log errors with context information
        
        Args:
            error_type (str): Type of error
            error_message (str): Error message
            context (dict): Additional context information
            hostname (str): Related hostname if applicable
        """
        with self.log_lock:
            self.event_counters['failures'] += 1
            
            log_entry = {
                'event_type': 'error',
                'session_id': self.session_id,
                'timestamp': datetime.now().isoformat(),
                'error_type': error_type,
                'error_message': error_message,
                'hostname': hostname,
                'context': context
            }
            
            message = "Error: %s - %s" % (error_type, error_message)
            if hostname:
                message = "Error on %s: %s - %s" % (hostname, error_type, error_message)
            
            self.app_logger.error(message)
            self.error_logger.error(json.dumps(log_entry))
            self.console_logger.error(message)
    
    def get_session_summary(self):
        """
        Get summary of current logging session
        
        Returns:
            dict: Session summary with statistics
        """
        duration = (datetime.now() - self.start_time).total_seconds()
        
        summary = {
            'session_id': self.session_id,
            'start_time': self.start_time.isoformat(),
            'duration_seconds': duration,
            'event_counters': self.event_counters.copy(),
            'log_directory': self.log_directory,
            'log_level': logging.getLevelName(self.log_level)
        }
        
        return summary
    
    def export_session_report(self, output_file=None):
        """
        Export detailed session report
        
        Args:
            output_file (str): Output filename (optional)
            
        Returns:
            dict: Complete session report
        """
        report = {
            'report_type': 'vlan_automation_session',
            'report_timestamp': datetime.now().isoformat(),
            'session_summary': self.get_session_summary(),
            'logging_configuration': {
                'log_directory': self.log_directory,
                'log_level': logging.getLevelName(self.log_level),
                'max_log_size': self.max_log_size,
                'backup_count': self.backup_count
            }
        }
        
        if output_file:
            try:
                with open(output_file, 'w') as f:
                    json.dump(report, f, indent=2, sort_keys=True)
            except IOError as e:
                self.log_error('report_export_error', str(e))
        
        return report
    
    def _generate_session_id(self):
        """Generate unique session ID"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        return 'session_%s' % timestamp
    
    def close(self):
        """Close all loggers and handlers"""
        self.app_logger.info("Logging session ended: %s" % self.session_id)
        
        # Close all handlers
        for logger_name in ['vlan_automation', 'vlan_audit', 'vlan_operations', 'vlan_errors', 'vlan_console']:
            logger = logging.getLogger(logger_name)
            for handler in logger.handlers:
                handler.close()


# Test and example usage
if __name__ == '__main__':
    print "VLAN Automation Logging System Test - March 8, 2013"
    print "===================================================="
    
    # Create test logger
    audit_logger = VLANAuditLogger(log_directory='./test_logs', log_level='DEBUG')
    
    try:
        print "Testing logging functionality..."
        
        # Test operation logging
        test_switches = [
            {'hostname': '192.168.1.10', 'username': 'admin'},
            {'hostname': '192.168.1.20', 'username': 'admin'}
        ]
        
        # Start operation
        audit_logger.log_operation_start(
            'create',
            test_switches,
            user='test_user',
            config_summary={'vlans': 3, 'interfaces': 5}
        )
        
        # Test connection logging
        audit_logger.log_switch_connection('192.168.1.10', 'success', connection_time=1.5)
        audit_logger.log_switch_connection('192.168.1.20', 'failed', error='Connection timeout')
        
        # Test configuration change logging
        audit_logger.log_configuration_change(
            '192.168.1.10',
            'vlan_create',
            {'vlan_id': 100, 'vlan_name': 'Test_VLAN'},
            success=True
        )
        
        # Test backup logging
        audit_logger.log_backup_operation(
            '192.168.1.10',
            'pre-change',
            'backup_20130308_144500',
            success=True
        )
        
        # Test validation logging
        audit_logger.log_validation_results(
            'test_config.json',
            'warning',
            issue_count=2,
            critical_issues=0
        )
        
        # Test error logging
        audit_logger.log_error(
            'ssh_connection_error',
            'Authentication failed',
            context={'retry_count': 3},
            hostname='192.168.1.20'
        )
        
        # Complete operation
        test_results = {
            'operation_id': 'op_20130308_144500',
            'status': 'partial',
            'summary': {
                'total_switches': 2,
                'successful_operations': 1,
                'failed_operations': 1
            }
        }
        
        audit_logger.log_operation_complete('create', test_results, duration=45.2)
        
        # Get session summary
        print "\nSession Summary:"
        summary = audit_logger.get_session_summary()
        for key, value in summary.items():
            if key != 'event_counters':
                print "  %s: %s" % (key, value)
        
        print "  Event Counters:"
        for event_type, count in summary['event_counters'].items():
            print "    %s: %d" % (event_type, count)
        
        # Export session report
        print "\nExporting session report..."
        report = audit_logger.export_session_report()
        print "Session report exported with %d event types" % len(summary['event_counters'])
        
        print "\nLogging test completed successfully!"
        
    finally:
        audit_logger.close()
        print "Logger closed"