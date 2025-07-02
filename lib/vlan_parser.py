#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
VLAN Configuration Parser
January 22, 2013 - Parse existing VLAN configurations from switches
Python 2.7 compatible parser for Cisco IOS VLAN configurations
"""

import re
import json
from datetime import datetime


class VLANParseError(Exception):
    """Custom exception for VLAN parsing errors"""
    pass


class CiscoVLANParser(object):
    """
    Parser for Cisco IOS VLAN configurations
    Extracts VLAN information from switch outputs
    """
    
    def __init__(self):
        """Initialize VLAN parser with regex patterns for 2013 IOS formats"""
        
        # VLAN brief output patterns (show vlan brief)
        self.vlan_brief_pattern = re.compile(
            r'^(\d+)\s+(\S+)\s+(\S+)\s+(.*)$',
            re.MULTILINE
        )
        
        # VLAN database patterns (show vlan)
        self.vlan_detail_pattern = re.compile(
            r'VLAN Name\s+Status\s+Ports\s*\n-+\s*\n(.*?)(?=\n\n|\nVLAN Type|\Z)',
            re.DOTALL
        )
        
        # Interface VLAN assignment patterns
        self.interface_vlan_pattern = re.compile(
            r'interface\s+(\S+).*?switchport\s+access\s+vlan\s+(\d+)',
            re.DOTALL | re.IGNORECASE
        )
        
        # Trunk interface patterns
        self.trunk_pattern = re.compile(
            r'interface\s+(\S+).*?switchport\s+mode\s+trunk',
            re.DOTALL | re.IGNORECASE
        )
        
        # Trunk allowed VLANs pattern
        self.trunk_vlans_pattern = re.compile(
            r'switchport\s+trunk\s+allowed\s+vlan\s+(.+)',
            re.IGNORECASE
        )
        
    def parse_vlan_brief(self, vlan_output):
        """
        Parse 'show vlan brief' output
        
        Args:
            vlan_output (str): Output from 'show vlan brief' command
            
        Returns:
            list: List of VLAN dictionaries
        """
        vlans = []
        
        if not vlan_output:
            return vlans
        
        # Split into lines and process
        lines = vlan_output.split('\n')
        in_vlan_section = False
        
        for line in lines:
            line = line.strip()
            
            # Skip header lines
            if 'VLAN Name' in line or '----' in line:
                in_vlan_section = True
                continue
            
            if not in_vlan_section or not line:
                continue
            
            # Parse VLAN line
            # Format: VLAN_ID  Name  Status  Ports
            parts = line.split()
            if len(parts) >= 3:
                try:
                    vlan_id = int(parts[0])
                    name = parts[1]
                    status = parts[2]
                    
                    # Collect ports (rest of the line)
                    ports = []
                    if len(parts) > 3:
                        ports = parts[3:]
                    
                    vlan = {
                        'id': vlan_id,
                        'name': name,
                        'status': status.lower(),
                        'ports': ports,
                        'type': 'ethernet'  # Default for most VLANs
                    }
                    
                    vlans.append(vlan)
                    
                except (ValueError, IndexError):
                    # Skip malformed lines
                    continue
        
        return vlans
    
    def parse_running_config_vlans(self, config_output):
        """
        Parse VLAN information from running configuration
        
        Args:
            config_output (str): Output from 'show running-config'
            
        Returns:
            dict: Parsed VLAN and interface information
        """
        result = {
            'vlans': {},
            'interfaces': {},
            'trunks': []
        }
        
        if not config_output:
            return result
        
        # Parse interface configurations
        interface_configs = self._extract_interface_configs(config_output)
        
        for interface_name, interface_config in interface_configs.items():
            interface_info = self._parse_interface_config(interface_name, interface_config)
            
            if interface_info:
                result['interfaces'][interface_name] = interface_info
                
                # Track trunk interfaces
                if interface_info.get('mode') == 'trunk':
                    result['trunks'].append({
                        'interface': interface_name,
                        'allowed_vlans': interface_info.get('allowed_vlans', []),
                        'native_vlan': interface_info.get('native_vlan')
                    })
        
        # Parse VLAN database entries (if present in config)
        vlan_configs = self._extract_vlan_configs(config_output)
        for vlan_id, vlan_config in vlan_configs.items():
            result['vlans'][vlan_id] = vlan_config
        
        return result
    
    def _extract_interface_configs(self, config_output):
        """Extract interface configurations from running config"""
        interfaces = {}
        
        # Pattern to match interface blocks
        interface_pattern = re.compile(
            r'^interface\s+(\S+)\s*\n((?:(?!^interface\s|^!|^end).+\n?)*)',
            re.MULTILINE | re.IGNORECASE
        )
        
        matches = interface_pattern.findall(config_output)
        
        for interface_name, interface_config in matches:
            # Only process switch interfaces (not loopback, etc.)
            if any(prefix in interface_name.lower() for prefix in 
                   ['fastethernet', 'gigabitethernet', 'ethernet', 'fe', 'gi', 'eth']):
                interfaces[interface_name] = interface_config
        
        return interfaces
    
    def _parse_interface_config(self, interface_name, interface_config):
        """Parse individual interface configuration"""
        interface_info = {
            'name': interface_name,
            'mode': 'access',  # Default mode
            'access_vlan': 1,  # Default VLAN
            'allowed_vlans': [],
            'native_vlan': None,
            'description': None,
            'status': 'up'
        }
        
        lines = interface_config.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Parse description
            if line.startswith('description'):
                interface_info['description'] = line.replace('description', '').strip()
            
            # Parse switchport mode
            elif 'switchport mode' in line:
                if 'trunk' in line:
                    interface_info['mode'] = 'trunk'
                elif 'access' in line:
                    interface_info['mode'] = 'access'
            
            # Parse access VLAN
            elif 'switchport access vlan' in line:
                try:
                    vlan_id = int(line.split()[-1])
                    interface_info['access_vlan'] = vlan_id
                except (ValueError, IndexError):
                    pass
            
            # Parse trunk allowed VLANs
            elif 'switchport trunk allowed vlan' in line:
                vlan_list = line.split('vlan')[-1].strip()
                interface_info['allowed_vlans'] = self._parse_vlan_list(vlan_list)
            
            # Parse native VLAN
            elif 'switchport trunk native vlan' in line:
                try:
                    native_vlan = int(line.split()[-1])
                    interface_info['native_vlan'] = native_vlan
                except (ValueError, IndexError):
                    pass
            
            # Parse shutdown status
            elif line == 'shutdown':
                interface_info['status'] = 'down'
        
        return interface_info
    
    def _extract_vlan_configs(self, config_output):
        """Extract VLAN database configurations (if present)"""
        vlans = {}
        
        # Look for VLAN configurations in the config
        # Note: In 2013, VLANs were often configured in VLAN database mode
        # but could also appear in global config
        
        vlan_pattern = re.compile(
            r'^vlan\s+(\d+)\s*\n((?:(?!^vlan\s|^!|^interface|^end).+\n?)*)',
            re.MULTILINE | re.IGNORECASE
        )
        
        matches = vlan_pattern.findall(config_output)
        
        for vlan_id, vlan_config in matches:
            vlan_info = {
                'id': int(vlan_id),
                'name': 'VLAN%s' % vlan_id,  # Default name
                'status': 'active'
            }
            
            # Parse VLAN configuration
            lines = vlan_config.split('\n')
            for line in lines:
                line = line.strip()
                
                if line.startswith('name'):
                    vlan_info['name'] = line.replace('name', '').strip()
                elif line.startswith('state'):
                    vlan_info['status'] = line.replace('state', '').strip()
            
            vlans[int(vlan_id)] = vlan_info
        
        return vlans
    
    def _parse_vlan_list(self, vlan_string):
        """
        Parse VLAN list string (e.g., "1-10,20,30-40")
        
        Args:
            vlan_string (str): VLAN list string
            
        Returns:
            list: List of VLAN IDs
        """
        vlans = []
        
        if not vlan_string or vlan_string.strip() == 'none':
            return vlans
        
        # Remove 'add' keyword if present
        vlan_string = vlan_string.replace('add', '').strip()
        
        # Split by commas
        parts = vlan_string.split(',')
        
        for part in parts:
            part = part.strip()
            
            if '-' in part:
                # Range of VLANs
                try:
                    start, end = part.split('-')
                    start = int(start.strip())
                    end = int(end.strip())
                    vlans.extend(range(start, end + 1))
                except (ValueError, IndexError):
                    pass
            else:
                # Single VLAN
                try:
                    vlan_id = int(part)
                    vlans.append(vlan_id)
                except ValueError:
                    pass
        
        return sorted(list(set(vlans)))  # Remove duplicates and sort
    
    def get_vlan_summary(self, vlans_data):
        """
        Generate summary of VLAN configuration
        
        Args:
            vlans_data (list): List of VLAN dictionaries
            
        Returns:
            dict: VLAN summary statistics
        """
        summary = {
            'total_vlans': len(vlans_data),
            'active_vlans': 0,
            'inactive_vlans': 0,
            'vlan_ranges': [],
            'name_patterns': {},
            'port_assignments': 0
        }
        
        vlan_ids = []
        
        for vlan in vlans_data:
            vlan_ids.append(vlan['id'])
            
            # Count status
            if vlan.get('status', 'active').lower() == 'active':
                summary['active_vlans'] += 1
            else:
                summary['inactive_vlans'] += 1
            
            # Count port assignments
            if vlan.get('ports'):
                summary['port_assignments'] += len(vlan['ports'])
            
            # Analyze naming patterns
            name = vlan.get('name', '')
            if name.startswith('VLAN'):
                pattern = 'default'
            elif any(keyword in name.lower() for keyword in ['guest', 'visitor']):
                pattern = 'guest'
            elif any(keyword in name.lower() for keyword in ['mgmt', 'management']):
                pattern = 'management'
            elif any(keyword in name.lower() for keyword in ['data', 'user']):
                pattern = 'data'
            else:
                pattern = 'custom'
            
            summary['name_patterns'][pattern] = summary['name_patterns'].get(pattern, 0) + 1
        
        # Find VLAN ranges
        if vlan_ids:
            vlan_ids.sort()
            summary['vlan_ranges'] = self._find_ranges(vlan_ids)
        
        return summary
    
    def _find_ranges(self, numbers):
        """Find consecutive ranges in a list of numbers"""
        ranges = []
        if not numbers:
            return ranges
        
        start = numbers[0]
        end = numbers[0]
        
        for i in range(1, len(numbers)):
            if numbers[i] == end + 1:
                end = numbers[i]
            else:
                if start == end:
                    ranges.append(str(start))
                else:
                    ranges.append('%d-%d' % (start, end))
                start = end = numbers[i]
        
        # Add the last range
        if start == end:
            ranges.append(str(start))
        else:
            ranges.append('%d-%d' % (start, end))
        
        return ranges
    
    def export_to_json(self, vlans_data, filename=None):
        """
        Export VLAN data to JSON format
        
        Args:
            vlans_data (dict): Parsed VLAN data
            filename (str): Output filename (optional)
            
        Returns:
            str: JSON string representation
        """
        export_data = {
            'export_timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'format_version': '1.0',
            'parser_version': 'CiscoVLANParser-2013.01.22',
            'data': vlans_data
        }
        
        json_output = json.dumps(export_data, indent=2, sort_keys=True)
        
        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write(json_output)
            except IOError as e:
                raise VLANParseError("Failed to write JSON file: %s" % str(e))
        
        return json_output


# Test and example usage
if __name__ == '__main__':
    print "Cisco VLAN Parser Test - January 22, 2013"
    print "=========================================="
    
    # Sample VLAN brief output for testing
    sample_vlan_brief = """
VLAN Name                             Status    Ports
---- -------------------------------- --------- -------------------------------
1    default                          active    Fa0/1, Fa0/2, Fa0/3, Fa0/4
10   Data_VLAN                        active    Fa0/5, Fa0/6, Fa0/7, Fa0/8
20   Voice_VLAN                       active    
30   Guest_VLAN                       active    Fa0/9, Fa0/10
100  Management_VLAN                  active    
200  DMZ_VLAN                         active    Fa0/11, Fa0/12
1002 fddi-default                     act/unsup 
1003 token-ring-default               act/unsup 
1004 fddinet-default                  act/unsup 
1005 trnet-default                    act/unsup 
"""
    
    # Test parser
    parser = CiscoVLANParser()
    
    print "Parsing sample VLAN brief output..."
    vlans = parser.parse_vlan_brief(sample_vlan_brief)
    
    print "Found %d VLANs:" % len(vlans)
    for vlan in vlans:
        print "  VLAN %d: %s (%s) - %d ports" % (
            vlan['id'], vlan['name'], vlan['status'], len(vlan['ports'])
        )
    
    # Generate summary
    print "\nVLAN Summary:"
    summary = parser.get_vlan_summary(vlans)
    for key, value in summary.items():
        if key != 'name_patterns':
            print "  %s: %s" % (key, value)
    
    print "  Name patterns:"
    for pattern, count in summary['name_patterns'].items():
        print "    %s: %d" % (pattern, count)
    
    # Test JSON export
    print "\nTesting JSON export..."
    json_output = parser.export_to_json({'vlans': vlans, 'summary': summary})
    print "JSON export successful (%d characters)" % len(json_output)
    
    print "\nParser test completed successfully!"