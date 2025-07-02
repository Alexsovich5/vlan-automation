#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
VLAN Configuration Validation Module
March 1, 2013 - Pre-flight validation and conflict detection
Python 2.7 compatible validation system for VLAN automation
"""

import re
import json
from datetime import datetime
from vlan_parser import CiscoVLANParser, VLANParseError


class ValidationError(Exception):
    """Custom exception for validation errors"""
    pass


class VLANConfigValidator(object):
    """
    VLAN configuration validator with comprehensive pre-flight checks
    Validates configurations before deployment to prevent conflicts
    """
    
    def __init__(self):
        """Initialize validation module with 2013 IOS standards"""
        
        # Validation rules for 2013 Cisco IOS
        self.validation_rules = {
            'vlan_id_range': {
                'normal': (1, 1005),
                'extended': (1006, 4094)
            },
            'reserved_vlans': [1002, 1003, 1004, 1005],  # Default reserved VLANs
            'max_vlan_name_length': 32,
            'max_description_length': 80,
            'interface_patterns': [
                r'^FastEthernet\d+/\d+(/\d+)?$',
                r'^GigabitEthernet\d+/\d+(/\d+)?$',
                r'^Ethernet\d+/\d+(/\d+)?$',
                r'^Fa\d+/\d+(/\d+)?$',
                r'^Gi\d+/\d+(/\d+)?$',
                r'^Eth\d+/\d+(/\d+)?$'
            ]
        }
        
        # Validation severity levels
        self.severity_levels = {
            'critical': 'Configuration will fail',
            'warning': 'Configuration may cause issues',
            'info': 'Configuration note'
        }
        
        # Initialize VLAN parser for existing config analysis
        self.vlan_parser = CiscoVLANParser()
    
    def validate_vlan_configuration(self, vlan_config, existing_config=None):
        """
        Validate complete VLAN configuration
        
        Args:
            vlan_config (dict): VLAN configuration to validate
            existing_config (dict): Existing switch configuration (optional)
            
        Returns:
            dict: Validation results with issues and recommendations
        """
        validation_results = {
            'timestamp': datetime.now().isoformat(),
            'validation_version': '1.0-2013.03.01',
            'overall_status': 'unknown',
            'issues': {
                'critical': [],
                'warning': [],
                'info': []
            },
            'statistics': {
                'total_vlans': 0,
                'total_interfaces': 0,
                'total_trunks': 0,
                'validation_checks': 0
            },
            'recommendations': []
        }
        
        try:
            # Validate VLAN definitions
            vlans = vlan_config.get('vlans', {}).get('vlans', [])
            validation_results['statistics']['total_vlans'] = len(vlans)
            
            for vlan in vlans:
                self._validate_single_vlan(vlan, validation_results, existing_config)
            
            # Validate interface configurations
            interfaces = vlan_config.get('interfaces', {}).get('interfaces', [])
            validation_results['statistics']['total_interfaces'] = len(interfaces)
            
            for interface in interfaces:
                self._validate_interface_config(interface, validation_results, vlans)
            
            # Validate trunk configurations
            trunks = vlan_config.get('trunks', {}).get('trunks', [])
            validation_results['statistics']['total_trunks'] = len(trunks)
            
            for trunk in trunks:
                self._validate_trunk_config(trunk, validation_results, vlans)
            
            # Cross-validation checks
            self._validate_vlan_consistency(vlan_config, validation_results)
            
            # Check for conflicts with existing configuration
            if existing_config:
                self._validate_against_existing_config(vlan_config, existing_config, validation_results)
            
            # Generate recommendations
            self._generate_recommendations(validation_results)
            
            # Determine overall status
            if validation_results['issues']['critical']:
                validation_results['overall_status'] = 'failed'
            elif validation_results['issues']['warning']:
                validation_results['overall_status'] = 'warning'
            else:
                validation_results['overall_status'] = 'passed'
            
            validation_results['statistics']['validation_checks'] = (
                len(validation_results['issues']['critical']) +
                len(validation_results['issues']['warning']) +
                len(validation_results['issues']['info'])
            )
            
        except Exception as e:
            validation_results['overall_status'] = 'error'
            validation_results['issues']['critical'].append({
                'type': 'validation_error',
                'message': 'Validation process failed: %s' % str(e),
                'location': 'validation_engine'
            })
        
        return validation_results
    
    def _validate_single_vlan(self, vlan, results, existing_config):
        """Validate individual VLAN configuration"""
        vlan_id = vlan.get('id')
        vlan_name = vlan.get('name')
        
        # Validate VLAN ID
        if not self._is_valid_vlan_id(vlan_id):
            results['issues']['critical'].append({
                'type': 'invalid_vlan_id',
                'message': 'Invalid VLAN ID: %s' % vlan_id,
                'location': 'vlan_%s' % vlan_id,
                'recommendation': 'Use VLAN ID between 1-1005 or 1006-4094'
            })
        
        # Check for reserved VLANs
        if vlan_id in self.validation_rules['reserved_vlans']:
            results['issues']['warning'].append({
                'type': 'reserved_vlan',
                'message': 'VLAN %d is reserved by system' % vlan_id,
                'location': 'vlan_%s' % vlan_id
            })
        
        # Validate VLAN name
        if vlan_name:
            if len(vlan_name) > self.validation_rules['max_vlan_name_length']:
                results['issues']['critical'].append({
                    'type': 'vlan_name_too_long',
                    'message': 'VLAN name "%s" exceeds %d characters' % (
                        vlan_name, self.validation_rules['max_vlan_name_length']
                    ),
                    'location': 'vlan_%s' % vlan_id
                })
            
            # Check for invalid characters in VLAN name
            if not re.match(r'^[a-zA-Z0-9_-]+$', vlan_name):
                results['issues']['critical'].append({
                    'type': 'invalid_vlan_name',
                    'message': 'VLAN name "%s" contains invalid characters' % vlan_name,
                    'location': 'vlan_%s' % vlan_id,
                    'recommendation': 'Use only alphanumeric characters, hyphens, and underscores'
                })
        
        # Check for VLAN 1 modification
        if vlan_id == 1:
            results['issues']['warning'].append({
                'type': 'default_vlan_modification',
                'message': 'Modifying default VLAN 1 is not recommended',
                'location': 'vlan_1'
            })
    
    def _validate_interface_config(self, interface, results, vlans):
        """Validate interface configuration"""
        interface_name = interface.get('name')
        vlan_id = interface.get('vlan_id')
        description = interface.get('description')
        
        # Validate interface name format
        if not self._is_valid_interface_name(interface_name):
            results['issues']['critical'].append({
                'type': 'invalid_interface_name',
                'message': 'Invalid interface name: %s' % interface_name,
                'location': 'interface_%s' % interface_name,
                'recommendation': 'Use standard Cisco interface naming (e.g., FastEthernet0/1)'
            })
        
        # Validate VLAN ID reference
        if not self._is_valid_vlan_id(vlan_id):
            results['issues']['critical'].append({
                'type': 'invalid_interface_vlan',
                'message': 'Interface %s references invalid VLAN %s' % (interface_name, vlan_id),
                'location': 'interface_%s' % interface_name
            })
        
        # Check if referenced VLAN exists in configuration
        vlan_ids = [v.get('id') for v in vlans]
        if vlan_id not in vlan_ids and vlan_id != 1:  # VLAN 1 always exists
            results['issues']['warning'].append({
                'type': 'missing_vlan_reference',
                'message': 'Interface %s references VLAN %d which is not defined' % (
                    interface_name, vlan_id
                ),
                'location': 'interface_%s' % interface_name,
                'recommendation': 'Ensure VLAN %d is created before interface assignment' % vlan_id
            })
        
        # Validate description length
        if description and len(description) > self.validation_rules['max_description_length']:
            results['issues']['warning'].append({
                'type': 'description_too_long',
                'message': 'Interface %s description exceeds %d characters' % (
                    interface_name, self.validation_rules['max_description_length']
                ),
                'location': 'interface_%s' % interface_name
            })
    
    def _validate_trunk_config(self, trunk, results, vlans):
        """Validate trunk configuration"""
        interface_name = trunk.get('interface')
        allowed_vlans = trunk.get('allowed_vlans', [])
        native_vlan = trunk.get('native_vlan')
        
        # Validate interface name
        if not self._is_valid_interface_name(interface_name):
            results['issues']['critical'].append({
                'type': 'invalid_trunk_interface',
                'message': 'Invalid trunk interface name: %s' % interface_name,
                'location': 'trunk_%s' % interface_name
            })
        
        # Validate allowed VLANs
        vlan_ids = [v.get('id') for v in vlans]
        
        for vlan_id in allowed_vlans:
            if not self._is_valid_vlan_id(vlan_id):
                results['issues']['critical'].append({
                    'type': 'invalid_trunk_vlan',
                    'message': 'Trunk %s allows invalid VLAN %s' % (interface_name, vlan_id),
                    'location': 'trunk_%s' % interface_name
                })
            elif vlan_id not in vlan_ids and vlan_id != 1:
                results['issues']['warning'].append({
                    'type': 'trunk_missing_vlan',
                    'message': 'Trunk %s allows VLAN %d which is not defined' % (
                        interface_name, vlan_id
                    ),
                    'location': 'trunk_%s' % interface_name
                })
        
        # Validate native VLAN
        if native_vlan:
            if not self._is_valid_vlan_id(native_vlan):
                results['issues']['critical'].append({
                    'type': 'invalid_native_vlan',
                    'message': 'Trunk %s has invalid native VLAN %s' % (interface_name, native_vlan),
                    'location': 'trunk_%s' % interface_name
                })
            elif native_vlan not in allowed_vlans:
                results['issues']['warning'].append({
                    'type': 'native_vlan_not_allowed',
                    'message': 'Trunk %s native VLAN %d is not in allowed VLANs list' % (
                        interface_name, native_vlan
                    ),
                    'location': 'trunk_%s' % interface_name
                })
    
    def _validate_vlan_consistency(self, vlan_config, results):
        """Validate consistency across VLAN configuration"""
        vlans = vlan_config.get('vlans', {}).get('vlans', [])
        interfaces = vlan_config.get('interfaces', {}).get('interfaces', [])
        trunks = vlan_config.get('trunks', {}).get('trunks', [])
        
        # Check for duplicate VLAN IDs
        vlan_ids = [v.get('id') for v in vlans]
        duplicate_vlans = [vid for vid in set(vlan_ids) if vlan_ids.count(vid) > 1]
        
        for vlan_id in duplicate_vlans:
            results['issues']['critical'].append({
                'type': 'duplicate_vlan_id',
                'message': 'VLAN ID %d is defined multiple times' % vlan_id,
                'location': 'vlan_definitions'
            })
        
        # Check for duplicate VLAN names
        vlan_names = [v.get('name') for v in vlans if v.get('name')]
        duplicate_names = [name for name in set(vlan_names) if vlan_names.count(name) > 1]
        
        for name in duplicate_names:
            results['issues']['critical'].append({
                'type': 'duplicate_vlan_name',
                'message': 'VLAN name "%s" is used multiple times' % name,
                'location': 'vlan_definitions'
            })
        
        # Check for duplicate interface assignments
        interface_names = [i.get('name') for i in interfaces]
        duplicate_interfaces = [name for name in set(interface_names) if interface_names.count(name) > 1]
        
        for interface_name in duplicate_interfaces:
            results['issues']['critical'].append({
                'type': 'duplicate_interface_config',
                'message': 'Interface %s is configured multiple times' % interface_name,
                'location': 'interface_definitions'
            })
        
        # Check for interface/trunk conflicts
        trunk_interfaces = [t.get('interface') for t in trunks]
        
        for interface in interfaces:
            if interface.get('name') in trunk_interfaces:
                results['issues']['critical'].append({
                    'type': 'interface_trunk_conflict',
                    'message': 'Interface %s is configured as both access and trunk' % interface.get('name'),
                    'location': 'interface_%s' % interface.get('name')
                })
    
    def _validate_against_existing_config(self, vlan_config, existing_config, results):
        """Validate against existing switch configuration"""
        try:
            # Parse existing VLAN configuration
            existing_vlans = self.vlan_parser.parse_vlan_brief(existing_config.get('vlan_brief', ''))
            existing_vlan_ids = [v['id'] for v in existing_vlans]
            
            # Check for VLAN conflicts
            new_vlans = vlan_config.get('vlans', {}).get('vlans', [])
            
            for vlan in new_vlans:
                vlan_id = vlan.get('id')
                
                if vlan_id in existing_vlan_ids:
                    # Find existing VLAN details
                    existing_vlan = next((v for v in existing_vlans if v['id'] == vlan_id), None)
                    
                    if existing_vlan:
                        if existing_vlan.get('name') != vlan.get('name'):
                            results['issues']['warning'].append({
                                'type': 'vlan_name_conflict',
                                'message': 'VLAN %d exists with different name: "%s" vs "%s"' % (
                                    vlan_id, existing_vlan.get('name'), vlan.get('name')
                                ),
                                'location': 'vlan_%s' % vlan_id
                            })
                        else:
                            results['issues']['info'].append({
                                'type': 'vlan_already_exists',
                                'message': 'VLAN %d already exists with same configuration' % vlan_id,
                                'location': 'vlan_%s' % vlan_id
                            })
            
        except Exception as e:
            results['issues']['warning'].append({
                'type': 'existing_config_parse_error',
                'message': 'Could not parse existing configuration: %s' % str(e),
                'location': 'existing_config_validation'
            })
    
    def _generate_recommendations(self, results):
        """Generate recommendations based on validation results"""
        recommendations = []
        
        # Critical issues recommendations
        if results['issues']['critical']:
            recommendations.append(
                'Critical issues detected - configuration will fail deployment'
            )
            recommendations.append(
                'Review and fix all critical issues before proceeding'
            )
        
        # Warning recommendations
        if results['issues']['warning']:
            recommendations.append(
                'Warning issues detected - review carefully before deployment'
            )
        
        # VLAN-specific recommendations
        total_vlans = results['statistics']['total_vlans']
        if total_vlans > 100:
            recommendations.append(
                'Large number of VLANs (%d) - consider network segmentation strategy' % total_vlans
            )
        
        # Interface recommendations
        total_interfaces = results['statistics']['total_interfaces']
        if total_interfaces > 48:
            recommendations.append(
                'Large number of interface configurations (%d) - consider batch deployment' % total_interfaces
            )
        
        # General recommendations
        if not results['issues']['critical'] and not results['issues']['warning']:
            recommendations.append('Configuration validation passed - ready for deployment')
        
        results['recommendations'] = recommendations
    
    def _is_valid_vlan_id(self, vlan_id):
        """Check if VLAN ID is valid according to 2013 standards"""
        if not isinstance(vlan_id, int):
            try:
                vlan_id = int(vlan_id)
            except (ValueError, TypeError):
                return False
        
        normal_range = self.validation_rules['vlan_id_range']['normal']
        extended_range = self.validation_rules['vlan_id_range']['extended']
        
        return (normal_range[0] <= vlan_id <= normal_range[1] or
                extended_range[0] <= vlan_id <= extended_range[1])
    
    def _is_valid_interface_name(self, interface_name):
        """Check if interface name is valid"""
        if not interface_name or not isinstance(interface_name, str):
            return False
        
        for pattern in self.validation_rules['interface_patterns']:
            if re.match(pattern, interface_name, re.IGNORECASE):
                return True
        
        return False
    
    def export_validation_report(self, validation_results, output_file=None):
        """
        Export validation report to JSON file
        
        Args:
            validation_results (dict): Validation results
            output_file (str): Output filename (optional)
            
        Returns:
            str: JSON report content
        """
        report = {
            'report_type': 'vlan_validation',
            'report_timestamp': datetime.now().isoformat(),
            'validation_results': validation_results,
            'summary': {
                'total_issues': sum(len(issues) for issues in validation_results['issues'].values()),
                'critical_issues': len(validation_results['issues']['critical']),
                'warning_issues': len(validation_results['issues']['warning']),
                'info_issues': len(validation_results['issues']['info']),
                'overall_status': validation_results['overall_status']
            }
        }
        
        json_content = json.dumps(report, indent=2, sort_keys=True)
        
        if output_file:
            try:
                with open(output_file, 'w') as f:
                    f.write(json_content)
            except IOError as e:
                raise ValidationError("Failed to export validation report: %s" % str(e))
        
        return json_content


# Test and example usage
if __name__ == '__main__':
    print "VLAN Configuration Validator Test - March 1, 2013"
    print "=================================================="
    
    # Sample VLAN configuration for testing
    sample_config = {
        'vlans': {
            'vlans': [
                {'id': 10, 'name': 'Data_VLAN'},
                {'id': 20, 'name': 'Voice_VLAN'},
                {'id': 30, 'name': 'Guest_VLAN'},
                {'id': 100, 'name': 'Management_VLAN'},
                {'id': 4095, 'name': 'Invalid_VLAN'},  # Invalid VLAN ID
                {'id': 50, 'name': 'Very_Long_VLAN_Name_That_Exceeds_Maximum_Length_Limit'}  # Invalid name
            ]
        },
        'interfaces': {
            'interfaces': [
                {'name': 'FastEthernet0/1', 'vlan_id': 10, 'description': 'Workstation Port'},
                {'name': 'FastEthernet0/2', 'vlan_id': 20, 'description': 'IP Phone Port'},
                {'name': 'FastEthernet0/3', 'vlan_id': 999, 'description': 'Invalid VLAN Reference'},
                {'name': 'InvalidInterface', 'vlan_id': 30, 'description': 'Invalid Interface Name'}
            ]
        },
        'trunks': {
            'trunks': [
                {
                    'interface': 'GigabitEthernet0/1',
                    'allowed_vlans': [10, 20, 30, 100],
                    'native_vlan': 1
                },
                {
                    'interface': 'FastEthernet0/1',  # Conflict with access interface
                    'allowed_vlans': [10, 20],
                    'native_vlan': 10
                }
            ]
        }
    }
    
    # Test validator
    validator = VLANConfigValidator()
    
    print "Validating sample configuration..."
    results = validator.validate_vlan_configuration(sample_config)
    
    print "\nValidation Results:"
    print "=================="
    print "Overall Status: %s" % results['overall_status']
    print "Total Issues: %d" % (len(results['issues']['critical']) + 
                                len(results['issues']['warning']) + 
                                len(results['issues']['info']))
    
    print "\nCritical Issues: %d" % len(results['issues']['critical'])
    for issue in results['issues']['critical']:
        print "  - %s: %s" % (issue['type'], issue['message'])
    
    print "\nWarning Issues: %d" % len(results['issues']['warning'])
    for issue in results['issues']['warning']:
        print "  - %s: %s" % (issue['type'], issue['message'])
    
    print "\nInfo Issues: %d" % len(results['issues']['info'])
    for issue in results['issues']['info']:
        print "  - %s: %s" % (issue['type'], issue['message'])
    
    print "\nRecommendations:"
    for recommendation in results['recommendations']:
        print "  - %s" % recommendation
    
    print "\nStatistics:"
    for key, value in results['statistics'].items():
        print "  %s: %s" % (key, value)
    
    # Test report export
    print "\nExporting validation report..."
    report_json = validator.export_validation_report(results)
    print "Report exported (%d characters)" % len(report_json)
    
    print "\nValidator test completed!"