#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Configuration Backup Manager
February 7, 2013 - Automated backup system for switch configurations
Python 2.7 compatible backup management for VLAN automation rollback
"""

import os
import json
import time
import shutil
import gzip
from datetime import datetime, timedelta


class BackupManagerError(Exception):
    """Custom exception for backup operations"""
    pass


class ConfigBackupManager(object):
    """
    Configuration backup manager for Cisco switches
    Handles backup creation, storage, and retrieval for rollback operations
    """
    
    def __init__(self, backup_directory='./backups', max_backups=50, compress_backups=True):
        """
        Initialize backup manager
        
        Args:
            backup_directory (str): Directory to store backups
            max_backups (int): Maximum number of backups to retain per switch
            compress_backups (bool): Whether to compress backup files
        """
        self.backup_directory = backup_directory
        self.max_backups = max_backups
        self.compress_backups = compress_backups
        
        # Ensure backup directory exists
        if not os.path.exists(self.backup_directory):
            try:
                os.makedirs(self.backup_directory)
            except OSError as e:
                raise BackupManagerError("Failed to create backup directory: %s" % str(e))
        
        # Backup file naming patterns (2013 style)
        self.timestamp_format = '%Y%m%d_%H%M%S'
        self.backup_filename_pattern = '{hostname}_{timestamp}.cfg'
        self.compressed_extension = '.gz'
        self.metadata_extension = '.json'
    
    def create_backup(self, hostname, configuration, backup_type='manual', description=None):
        """
        Create configuration backup for a switch
        
        Args:
            hostname (str): Switch hostname or IP address
            configuration (str): Configuration content to backup
            backup_type (str): Type of backup ('manual', 'auto', 'pre-change')
            description (str): Optional backup description
            
        Returns:
            dict: Backup information including filename and metadata
            
        Raises:
            BackupManagerError: If backup creation fails
        """
        if not hostname or not configuration:
            raise BackupManagerError("Hostname and configuration required for backup")
        
        # Generate timestamp and filename
        timestamp = datetime.now().strftime(self.timestamp_format)
        base_filename = self.backup_filename_pattern.format(
            hostname=self._sanitize_hostname(hostname),
            timestamp=timestamp
        )
        
        # Create switch-specific directory
        switch_backup_dir = os.path.join(self.backup_directory, self._sanitize_hostname(hostname))
        if not os.path.exists(switch_backup_dir):
            try:
                os.makedirs(switch_backup_dir)
            except OSError as e:
                raise BackupManagerError("Failed to create switch backup directory: %s" % str(e))
        
        # Prepare backup metadata
        backup_metadata = {
            'hostname': hostname,
            'timestamp': timestamp,
            'backup_type': backup_type,
            'description': description or 'Automated backup',
            'configuration_size': len(configuration),
            'compressed': self.compress_backups,
            'created_date': datetime.now().isoformat(),
            'backup_version': '1.0-2013.02.07'
        }
        
        try:
            # Write configuration file
            config_filename = os.path.join(switch_backup_dir, base_filename)
            
            if self.compress_backups:
                config_filename += self.compressed_extension
                with gzip.open(config_filename, 'wb') as f:
                    f.write(configuration)
            else:
                with open(config_filename, 'w') as f:
                    f.write(configuration)
            
            # Write metadata file
            metadata_filename = os.path.join(switch_backup_dir, 
                                           base_filename + self.metadata_extension)
            with open(metadata_filename, 'w') as f:
                json.dump(backup_metadata, f, indent=2, sort_keys=True)
            
            # Update backup metadata
            backup_metadata['config_filename'] = config_filename
            backup_metadata['metadata_filename'] = metadata_filename
            backup_metadata['backup_id'] = '%s_%s' % (self._sanitize_hostname(hostname), timestamp)
            
            # Clean up old backups
            self._cleanup_old_backups(switch_backup_dir)
            
            return backup_metadata
            
        except Exception as e:
            raise BackupManagerError("Failed to create backup: %s" % str(e))
    
    def list_backups(self, hostname=None, backup_type=None, days_back=None):
        """
        List available backups
        
        Args:
            hostname (str): Filter by hostname (optional)
            backup_type (str): Filter by backup type (optional)
            days_back (int): Only show backups within N days (optional)
            
        Returns:
            list: List of backup metadata dictionaries
        """
        backups = []
        
        # Determine which directories to search
        if hostname:
            search_dirs = [os.path.join(self.backup_directory, self._sanitize_hostname(hostname))]
        else:
            search_dirs = []
            if os.path.exists(self.backup_directory):
                for item in os.listdir(self.backup_directory):
                    item_path = os.path.join(self.backup_directory, item)
                    if os.path.isdir(item_path):
                        search_dirs.append(item_path)
        
        # Search for backup metadata files
        for search_dir in search_dirs:
            if not os.path.exists(search_dir):
                continue
            
            for filename in os.listdir(search_dir):
                if filename.endswith(self.metadata_extension):
                    metadata_path = os.path.join(search_dir, filename)
                    
                    try:
                        with open(metadata_path, 'r') as f:
                            metadata = json.load(f)
                        
                        # Apply filters
                        if backup_type and metadata.get('backup_type') != backup_type:
                            continue
                        
                        if days_back:
                            backup_date = datetime.strptime(metadata['timestamp'], self.timestamp_format)
                            cutoff_date = datetime.now() - timedelta(days=days_back)
                            if backup_date < cutoff_date:
                                continue
                        
                        # Verify backup file exists
                        config_file = metadata.get('config_filename')
                        if config_file and os.path.exists(config_file):
                            backups.append(metadata)
                        
                    except (IOError, ValueError, KeyError):
                        # Skip corrupted metadata files
                        continue
        
        # Sort by timestamp (newest first)
        backups.sort(key=lambda x: x['timestamp'], reverse=True)
        return backups
    
    def restore_backup(self, backup_id):
        """
        Restore configuration from backup
        
        Args:
            backup_id (str): Backup ID to restore
            
        Returns:
            str: Configuration content
            
        Raises:
            BackupManagerError: If backup cannot be restored
        """
        # Find backup metadata
        backup_metadata = self._find_backup_by_id(backup_id)
        if not backup_metadata:
            raise BackupManagerError("Backup not found: %s" % backup_id)
        
        config_filename = backup_metadata['config_filename']
        
        try:
            if backup_metadata.get('compressed'):
                with gzip.open(config_filename, 'rb') as f:
                    configuration = f.read()
            else:
                with open(config_filename, 'r') as f:
                    configuration = f.read()
                    
            return configuration
            
        except IOError as e:
            raise BackupManagerError("Failed to restore backup: %s" % str(e))
    
    def delete_backup(self, backup_id):
        """
        Delete a specific backup
        
        Args:
            backup_id (str): Backup ID to delete
            
        Returns:
            bool: True if deletion successful
            
        Raises:
            BackupManagerError: If backup cannot be deleted
        """
        backup_metadata = self._find_backup_by_id(backup_id)
        if not backup_metadata:
            raise BackupManagerError("Backup not found: %s" % backup_id)
        
        try:
            # Delete configuration file
            config_file = backup_metadata['config_filename']
            if os.path.exists(config_file):
                os.remove(config_file)
            
            # Delete metadata file
            metadata_file = backup_metadata['metadata_filename']
            if os.path.exists(metadata_file):
                os.remove(metadata_file)
            
            return True
            
        except OSError as e:
            raise BackupManagerError("Failed to delete backup: %s" % str(e))
    
    def get_backup_statistics(self, hostname=None):
        """
        Get backup statistics
        
        Args:
            hostname (str): Filter by hostname (optional)
            
        Returns:
            dict: Backup statistics
        """
        backups = self.list_backups(hostname=hostname)
        
        stats = {
            'total_backups': len(backups),
            'backup_types': {},
            'oldest_backup': None,
            'newest_backup': None,
            'total_size_bytes': 0,
            'switches_with_backups': set()
        }
        
        if not backups:
            return stats
        
        for backup in backups:
            # Count backup types
            backup_type = backup.get('backup_type', 'unknown')
            stats['backup_types'][backup_type] = stats['backup_types'].get(backup_type, 0) + 1
            
            # Track switches
            stats['switches_with_backups'].add(backup['hostname'])
            
            # Calculate size
            config_file = backup.get('config_filename')
            if config_file and os.path.exists(config_file):
                stats['total_size_bytes'] += os.path.getsize(config_file)
        
        # Convert set to count
        stats['switches_with_backups'] = len(stats['switches_with_backups'])
        
        # Find oldest and newest
        if backups:
            stats['oldest_backup'] = backups[-1]['timestamp']
            stats['newest_backup'] = backups[0]['timestamp']
        
        return stats
    
    def cleanup_expired_backups(self, retention_days=30):
        """
        Clean up backups older than retention period
        
        Args:
            retention_days (int): Number of days to retain backups
            
        Returns:
            dict: Cleanup results
        """
        cutoff_date = datetime.now() - timedelta(days=retention_days)
        deleted_count = 0
        error_count = 0
        
        all_backups = self.list_backups()
        
        for backup in all_backups:
            try:
                backup_date = datetime.strptime(backup['timestamp'], self.timestamp_format)
                
                if backup_date < cutoff_date:
                    self.delete_backup(backup['backup_id'])
                    deleted_count += 1
                    
            except Exception:
                error_count += 1
                continue
        
        return {
            'deleted_count': deleted_count,
            'error_count': error_count,
            'retention_days': retention_days,
            'cutoff_date': cutoff_date.strftime(self.timestamp_format)
        }
    
    def _sanitize_hostname(self, hostname):
        """Sanitize hostname for use in filenames"""
        # Replace problematic characters for filesystem compatibility
        sanitized = hostname.replace(':', '_').replace('/', '_').replace('\\', '_')
        sanitized = ''.join(c for c in sanitized if c.isalnum() or c in '._-')
        return sanitized[:50]  # Limit length
    
    def _find_backup_by_id(self, backup_id):
        """Find backup metadata by backup ID"""
        all_backups = self.list_backups()
        
        for backup in all_backups:
            if backup.get('backup_id') == backup_id:
                return backup
        
        return None
    
    def _cleanup_old_backups(self, switch_backup_dir):
        """Clean up old backups for a specific switch"""
        if self.max_backups <= 0:
            return
        
        # Get all backup files for this switch
        backup_files = []
        
        for filename in os.listdir(switch_backup_dir):
            if filename.endswith(self.metadata_extension):
                metadata_path = os.path.join(switch_backup_dir, filename)
                
                try:
                    with open(metadata_path, 'r') as f:
                        metadata = json.load(f)
                    
                    backup_files.append({
                        'timestamp': metadata['timestamp'],
                        'metadata_file': metadata_path,
                        'config_file': metadata.get('config_filename')
                    })
                    
                except (IOError, ValueError):
                    continue
        
        # Sort by timestamp (oldest first)
        backup_files.sort(key=lambda x: x['timestamp'])
        
        # Delete oldest backups if we exceed the limit
        while len(backup_files) > self.max_backups:
            old_backup = backup_files.pop(0)
            
            try:
                # Delete metadata file
                if os.path.exists(old_backup['metadata_file']):
                    os.remove(old_backup['metadata_file'])
                
                # Delete config file
                if old_backup['config_file'] and os.path.exists(old_backup['config_file']):
                    os.remove(old_backup['config_file'])
                    
            except OSError:
                # Continue cleanup even if some files can't be deleted
                continue
    
    def export_backup_report(self, output_file=None):
        """
        Export backup report to JSON file
        
        Args:
            output_file (str): Output filename (optional)
            
        Returns:
            dict: Complete backup report
        """
        report = {
            'report_timestamp': datetime.now().isoformat(),
            'backup_directory': self.backup_directory,
            'backup_settings': {
                'max_backups': self.max_backups,
                'compress_backups': self.compress_backups
            },
            'statistics': self.get_backup_statistics(),
            'backups': self.list_backups()
        }
        
        if output_file:
            try:
                with open(output_file, 'w') as f:
                    json.dump(report, f, indent=2, sort_keys=True)
            except IOError as e:
                raise BackupManagerError("Failed to export report: %s" % str(e))
        
        return report


# Test and example usage
if __name__ == '__main__':
    print "Configuration Backup Manager Test - February 7, 2013"
    print "======================================================"
    
    # Create test backup manager
    backup_manager = ConfigBackupManager(backup_directory='./test_backups')
    
    # Sample configuration for testing
    sample_config = """version 12.2
no service pad
service timestamps debug datetime msec
service timestamps log datetime msec
no service password-encryption
!
hostname TestSwitch
!
boot-start-marker
boot-end-marker
!
username admin privilege 15 secret 5 $1$mERr$hx5rVt7rPNoS4wqbXKX7m0
!
vlan internal allocation policy ascending
!
vlan 10
 name Data_VLAN
!
vlan 20
 name Voice_VLAN
!
interface FastEthernet0/1
 switchport access vlan 10
 switchport mode access
!
interface GigabitEthernet0/1
 switchport trunk allowed vlan 1,10,20
 switchport mode trunk
!
line con 0
line vty 0 4
 login local
 transport input ssh
!
end"""
    
    try:
        print "Creating test backup..."
        backup_info = backup_manager.create_backup(
            hostname='192.168.1.10',
            configuration=sample_config,
            backup_type='pre-change',
            description='Test backup before VLAN automation'
        )
        
        print "Backup created successfully:"
        print "  Backup ID: %s" % backup_info['backup_id']
        print "  File: %s" % backup_info['config_filename']
        print "  Size: %s bytes" % backup_info['configuration_size']
        print "  Compressed: %s" % backup_info['compressed']
        
        # List backups
        print "\nListing all backups..."
        backups = backup_manager.list_backups()
        print "Found %d backup(s):" % len(backups)
        
        for backup in backups[:3]:  # Show first 3
            print "  %s - %s (%s)" % (
                backup['backup_id'], 
                backup['hostname'], 
                backup['backup_type']
            )
        
        # Test backup restoration
        print "\nTesting backup restoration..."
        restored_config = backup_manager.restore_backup(backup_info['backup_id'])
        print "Restored configuration (%d bytes)" % len(restored_config)
        
        # Get statistics
        print "\nBackup statistics:"
        stats = backup_manager.get_backup_statistics()
        for key, value in stats.items():
            if key != 'backup_types':
                print "  %s: %s" % (key, value)
        
        print "  Backup types:"
        for backup_type, count in stats['backup_types'].items():
            print "    %s: %d" % (backup_type, count)
        
        # Test report export
        print "\nExporting backup report..."
        report = backup_manager.export_backup_report()
        print "Report generated with %d total backups" % len(report['backups'])
        
        print "\nBackup manager test completed successfully!"
        
    except BackupManagerError as e:
        print "Backup Error: %s" % str(e)
    except Exception as e:
        print "Unexpected error: %s" % str(e)