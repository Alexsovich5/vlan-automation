#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Cisco IOS Configuration Builder
January 30, 2013 - Generate Cisco IOS commands for VLAN operations
Python 2.7 compatible configuration generator for switch automation
"""

import json
import re
from datetime import datetime


class ConfigBuilderError(Exception):
    """Custom exception for configuration building errors"""
    pass


class CiscoConfigBuilder(object):
    """
    Cisco IOS configuration command builder
    Generates configuration commands for VLAN management operations
    """
    
    def __init__(self):
        """Initialize configuration builder with IOS command templates"""
        
        # Command templates for 2013 Cisco IOS
        self.templates = {
            'vlan_create': [
                'vlan {vlan_id}',
                'name {vlan_name}',
                'state active',
                'exit'
            ],
            'vlan_delete': [
                'no vlan {vlan_id}'
            ],
            'interface_access': [
                'interface {interface}',
                'switchport mode access',
                'switchport access vlan {vlan_id}',
                'exit'
            ],
            'interface_trunk': [
                'interface {interface}',
                'switchport mode trunk',
                'switchport trunk allowed vlan {allowed_vlans}',
                'exit'
            ],
            'interface_trunk_native': [
                'interface {interface}',
                'switchport trunk native vlan {native_vlan}',
                'exit'
            ]
        }
        
        # Valid VLAN ID ranges (2013 standards)
        self.vlan_ranges = {
            'normal': (1, 1005),
            'extended': (1006, 4094)
        }
        
        # Default VLAN names pattern
        self.default_vlan_pattern = 'VLAN{vlan_id:04d}'
        
    def create_vlan_commands(self, vlan_config):
        """
        Generate commands to create VLANs
        
        Args:
            vlan_config (dict): VLAN configuration
            
        Returns:
            list: List of IOS commands
            
        Raises:
            ConfigBuilderError: If configuration is invalid
        """
        commands = []
        
        if not isinstance(vlan_config, dict):
            raise ConfigBuilderError("VLAN configuration must be a dictionary")
        
        vlans = vlan_config.get('vlans', [])
        if not vlans:
            return commands
        
        # Process each VLAN
        for vlan in vlans:
            vlan_commands = self._build_vlan_create(vlan)
            commands.extend(vlan_commands)
        
        return commands
    
    def delete_vlan_commands(self, vlan_ids):
        """
        Generate commands to delete VLANs
        
        Args:
            vlan_ids (list): List of VLAN IDs to delete
            
        Returns:
            list: List of IOS commands
        """
        commands = []
        
        if not isinstance(vlan_ids, (list, tuple)):
            vlan_ids = [vlan_ids]
        
        for vlan_id in vlan_ids:
            if self._validate_vlan_id(vlan_id):
                command = self.templates['vlan_delete'][0].format(vlan_id=vlan_id)
                commands.append(command)
        
        return commands
    
    def configure_interface_access(self, interface_config):
        """
        Generate commands to configure access interfaces
        
        Args:
            interface_config (dict): Interface configuration
            
        Returns:
            list: List of IOS commands
        """
        commands = []
        
        if not isinstance(interface_config, dict):
            raise ConfigBuilderError("Interface configuration must be a dictionary")
        
        interfaces = interface_config.get('interfaces', [])
        
        for interface in interfaces:
            interface_commands = self._build_interface_access(interface)
            commands.extend(interface_commands)
        
        return commands
    
    def configure_interface_trunk(self, trunk_config):
        """
        Generate commands to configure trunk interfaces
        
        Args:
            trunk_config (dict): Trunk configuration
            
        Returns:
            list: List of IOS commands
        """
        commands = []
        
        if not isinstance(trunk_config, dict):
            raise ConfigBuilderError("Trunk configuration must be a dictionary")
        
        trunks = trunk_config.get('trunks', [])
        
        for trunk in trunks:
            trunk_commands = self._build_interface_trunk(trunk)
            commands.extend(trunk_commands)
        
        return commands
    
    def build_complete_config(self, config_data):
        """
        Build complete configuration from JSON config data
        
        Args:
            config_data (dict): Complete configuration data
            
        Returns:
            dict: Configuration commands organized by operation type
        """
        result = {
            'vlans': [],
            'interfaces': [],
            'trunks': [],
            'validation_commands': [],
            'rollback_commands': []
        }
        
        try:
            # Build VLAN creation commands
            if 'vlans' in config_data:
                result['vlans'] = self.create_vlan_commands(config_data)
            
            # Build interface access commands
            if 'interfaces' in config_data:
                result['interfaces'] = self.configure_interface_access(config_data)
            
            # Build trunk commands
            if 'trunks' in config_data:
                result['trunks'] = self.configure_interface_trunk(config_data)
            
            # Generate validation commands
            result['validation_commands'] = self._build_validation_commands(config_data)
            
            # Generate rollback commands
            result['rollback_commands'] = self._build_rollback_commands(config_data)
            
        except Exception as e:
            raise ConfigBuilderError("Failed to build configuration: %s" % str(e))
        
        return result
    
    def _build_vlan_create(self, vlan):
        """Build commands for creating a single VLAN"""
        commands = []
        
        vlan_id = vlan.get('id')
        if not self._validate_vlan_id(vlan_id):
            raise ConfigBuilderError("Invalid VLAN ID: %s" % vlan_id)
        
        vlan_name = vlan.get('name')
        if not vlan_name:
            vlan_name = self.default_vlan_pattern.format(vlan_id=vlan_id)
        
        # Validate VLAN name (2013 IOS limitations)
        if not self._validate_vlan_name(vlan_name):
            raise ConfigBuilderError("Invalid VLAN name: %s" % vlan_name)
        
        # Generate VLAN creation commands
        for template_line in self.templates['vlan_create']:
            command = template_line.format(
                vlan_id=vlan_id,
                vlan_name=vlan_name
            )
            commands.append(command)
        
        return commands
    
    def _build_interface_access(self, interface):
        """Build commands for configuring access interface"""
        commands = []
        
        interface_name = interface.get('name')
        vlan_id = interface.get('vlan_id')
        
        if not interface_name or not vlan_id:
            raise ConfigBuilderError("Interface name and VLAN ID required")
        
        if not self._validate_interface_name(interface_name):
            raise ConfigBuilderError("Invalid interface name: %s" % interface_name)
        
        if not self._validate_vlan_id(vlan_id):
            raise ConfigBuilderError("Invalid VLAN ID: %s" % vlan_id)
        
        # Generate interface access commands
        for template_line in self.templates['interface_access']:
            command = template_line.format(
                interface=interface_name,
                vlan_id=vlan_id
            )
            commands.append(command)
        
        # Add description if provided
        description = interface.get('description')
        if description:
            commands.insert(-1, 'description %s' % description)
        
        return commands
    
    def _build_interface_trunk(self, trunk):
        """Build commands for configuring trunk interface"""
        commands = []
        
        interface_name = trunk.get('interface')
        allowed_vlans = trunk.get('allowed_vlans', [])
        native_vlan = trunk.get('native_vlan')
        
        if not interface_name:
            raise ConfigBuilderError("Interface name required for trunk")
        
        if not self._validate_interface_name(interface_name):
            raise ConfigBuilderError("Invalid interface name: %s" % interface_name)
        
        # Build VLAN list string
        vlan_list = self._build_vlan_list_string(allowed_vlans)
        
        # Generate trunk commands
        for template_line in self.templates['interface_trunk']:
            command = template_line.format(
                interface=interface_name,
                allowed_vlans=vlan_list
            )
            commands.append(command)
        
        # Add native VLAN if specified
        if native_vlan:
            if self._validate_vlan_id(native_vlan):
                native_commands = []
                for template_line in self.templates['interface_trunk_native']:
                    command = template_line.format(
                        interface=interface_name,
                        native_vlan=native_vlan
                    )
                    native_commands.append(command)
                commands.extend(native_commands)
        
        return commands
    
    def _build_validation_commands(self, config_data):
        """Build commands for validating configuration"""
        commands = [
            'show vlan brief',
            'show interfaces status',
            'show interfaces trunk'
        ]
        
        # Add specific VLAN checks
        vlans = config_data.get('vlans', {}).get('vlans', [])
        for vlan in vlans:
            vlan_id = vlan.get('id')
            if vlan_id:
                commands.append('show vlan id %d' % vlan_id)
        
        return commands
    
    def _build_rollback_commands(self, config_data):
        """Build commands for rolling back configuration"""
        rollback_commands = []
        
        # Generate VLAN deletion commands for rollback
        vlans = config_data.get('vlans', {}).get('vlans', [])
        for vlan in vlans:
            vlan_id = vlan.get('id')
            if vlan_id and vlan_id > 1:  # Don't delete default VLAN
                rollback_commands.append('no vlan %d' % vlan_id)
        
        # Generate interface reset commands
        interfaces = config_data.get('interfaces', {}).get('interfaces', [])
        for interface in interfaces:
            interface_name = interface.get('name')
            if interface_name:
                rollback_commands.extend([
                    'interface %s' % interface_name,
                    'switchport access vlan 1',
                    'no description',
                    'exit'
                ])
        
        return rollback_commands
    
    def _validate_vlan_id(self, vlan_id):
        """Validate VLAN ID according to 2013 standards"""
        if not isinstance(vlan_id, int):
            try:
                vlan_id = int(vlan_id)
            except (ValueError, TypeError):
                return False
        
        # Check standard ranges
        normal_range = self.vlan_ranges['normal']
        extended_range = self.vlan_ranges['extended']
        
        return (normal_range[0] <= vlan_id <= normal_range[1] or
                extended_range[0] <= vlan_id <= extended_range[1])
    
    def _validate_vlan_name(self, vlan_name):
        """Validate VLAN name according to IOS restrictions"""
        if not vlan_name or not isinstance(vlan_name, str):
            return False
        
        # 2013 IOS VLAN name restrictions
        if len(vlan_name) > 32:
            return False
        
        # Only alphanumeric, hyphen, underscore allowed
        if not re.match(r'^[a-zA-Z0-9_-]+$', vlan_name):
            return False
        
        return True
    
    def _validate_interface_name(self, interface_name):
        """Validate interface name format"""
        if not interface_name or not isinstance(interface_name, str):
            return False
        
        # Common 2013 interface patterns
        valid_patterns = [
            r'^FastEthernet\d+/\d+(/\d+)?$',
            r'^GigabitEthernet\d+/\d+(/\d+)?$',
            r'^Ethernet\d+/\d+(/\d+)?$',
            r'^Fa\d+/\d+(/\d+)?$',
            r'^Gi\d+/\d+(/\d+)?$',
            r'^Eth\d+/\d+(/\d+)?$'
        ]
        
        for pattern in valid_patterns:
            if re.match(pattern, interface_name, re.IGNORECASE):
                return True
        
        return False
    
    def _build_vlan_list_string(self, vlan_list):
        """Build VLAN list string for trunk configuration"""
        if not vlan_list:
            return 'all'
        
        if not isinstance(vlan_list, (list, tuple)):
            vlan_list = [vlan_list]
        
        # Sort and create ranges
        vlans = sorted([int(v) for v in vlan_list if self._validate_vlan_id(v)])
        
        if not vlans:
            return 'none'
        
        # Group consecutive VLANs into ranges
        ranges = []
        start = vlans[0]
        end = vlans[0]
        
        for i in range(1, len(vlans)):
            if vlans[i] == end + 1:
                end = vlans[i]
            else:
                if start == end:
                    ranges.append(str(start))
                else:
                    ranges.append('%d-%d' % (start, end))
                start = end = vlans[i]
        
        # Add the last range
        if start == end:
            ranges.append(str(start))
        else:
            ranges.append('%d-%d' % (start, end))
        
        return ','.join(ranges)
    
    def export_config_script(self, commands, filename=None, include_header=True):
        """
        Export configuration commands as a script file
        
        Args:
            commands (list): List of IOS commands
            filename (str): Output filename (optional)
            include_header (bool): Include script header
            
        Returns:
            str: Configuration script content
        """
        script_lines = []
        
        if include_header:
            script_lines.extend([
                '! Cisco IOS Configuration Script',
                '! Generated by VLAN Automation Tool',
                '! Date: %s' % datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                '! Python 2.7 Compatible - January 30, 2013',
                '!',
                'configure terminal',
                '!'
            ])
        
        # Add commands
        for command in commands:
            if command.strip():
                script_lines.append(command)
        
        if include_header:
            script_lines.extend([
                '!',
                'end',
                'copy running-config startup-config',
                '!'
            ])
        
        script_content = '\n'.join(script_lines)
        
        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write(script_content)
            except IOError as e:
                raise ConfigBuilderError("Failed to write script file: %s" % str(e))
        
        return script_content
    
    def get_config_summary(self, config_commands):
        """
        Generate summary of configuration changes
        
        Args:
            config_commands (dict): Configuration commands by type
            
        Returns:
            dict: Summary statistics
        """
        summary = {
            'total_commands': 0,
            'vlan_operations': 0,
            'interface_operations': 0,
            'trunk_operations': 0,
            'validation_checks': 0,
            'estimated_time_minutes': 0
        }
        
        for operation_type, commands in config_commands.items():
            command_count = len(commands) if isinstance(commands, list) else 0
            summary['total_commands'] += command_count
            
            if operation_type == 'vlans':
                summary['vlan_operations'] = command_count
            elif operation_type == 'interfaces':
                summary['interface_operations'] = command_count
            elif operation_type == 'trunks':
                summary['trunk_operations'] = command_count
            elif operation_type == 'validation_commands':
                summary['validation_checks'] = command_count
        
        # Estimate execution time (rough calculation for 2013)
        summary['estimated_time_minutes'] = max(1, summary['total_commands'] // 10)
        
        return summary


# Test and example usage
if __name__ == '__main__':
    print "Cisco Configuration Builder Test - January 30, 2013"
    print "==================================================="
    
    # Sample configuration data
    sample_config = {
        'vlans': {
            'vlans': [
                {'id': 10, 'name': 'Data_VLAN'},
                {'id': 20, 'name': 'Voice_VLAN'},
                {'id': 30, 'name': 'Guest_VLAN'},
                {'id': 100, 'name': 'Management_VLAN'}
            ]
        },
        'interfaces': {
            'interfaces': [
                {'name': 'FastEthernet0/1', 'vlan_id': 10, 'description': 'Workstation Port'},
                {'name': 'FastEthernet0/2', 'vlan_id': 20, 'description': 'IP Phone Port'},
                {'name': 'FastEthernet0/3', 'vlan_id': 30, 'description': 'Guest Access'}
            ]
        },
        'trunks': {
            'trunks': [
                {
                    'interface': 'GigabitEthernet0/1',
                    'allowed_vlans': [10, 20, 30, 100],
                    'native_vlan': 1
                }
            ]
        }
    }
    
    # Test configuration builder
    builder = CiscoConfigBuilder()
    
    print "Building complete configuration..."
    config_commands = builder.build_complete_config(sample_config)
    
    print "\nGenerated Commands Summary:"
    for operation_type, commands in config_commands.items():
        print "  %s: %d commands" % (operation_type, len(commands))
    
    print "\nSample VLAN Creation Commands:"
    for command in config_commands['vlans'][:10]:
        print "  %s" % command
    
    print "\nSample Interface Commands:"
    for command in config_commands['interfaces'][:8]:
        print "  %s" % command
    
    # Test configuration script export
    print "\nTesting script export..."
    all_commands = []
    for commands in config_commands.values():
        if isinstance(commands, list):
            all_commands.extend(commands)
    
    script_content = builder.export_config_script(all_commands[:20])  # First 20 commands
    print "Script generated (%d lines)" % len(script_content.split('\n'))
    
    # Generate summary
    summary = builder.get_config_summary(config_commands)
    print "\nConfiguration Summary:"
    for key, value in summary.items():
        print "  %s: %s" % (key, value)
    
    print "\nConfiguration builder test completed successfully!"