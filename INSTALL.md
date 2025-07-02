# VLAN Configuration Automation Tool - Installation Guide

## System Requirements

### Operating System
- CentOS 6.x or Red Hat Enterprise Linux 6.x
- Ubuntu 12.04 LTS or later
- Any Linux distribution with Python 2.7 support

### Software Dependencies
- Python 2.7.3 or later (Python 2.x series)
- Paramiko 1.10.1 for SSH connectivity
- Git for version control

### Network Requirements
- SSH access to Cisco switches (port 22)
- Network connectivity between automation host and target switches
- Sufficient privileges on switches for configuration changes

## Installation Steps

### 1. System Preparation

Update your system package manager:
```bash
# CentOS/RHEL
sudo yum update

# Ubuntu/Debian  
sudo apt-get update
```

Install Python development tools:
```bash
# CentOS/RHEL
sudo yum install python-devel python-pip git

# Ubuntu/Debian
sudo apt-get install python-dev python-pip git
```

### 2. Install Python Dependencies

Install Paramiko SSH library:
```bash
sudo pip install paramiko==1.10.1
```

Verify installation:
```bash
python -c "import paramiko; print paramiko.__version__"
```

### 3. Download and Install VLAN Automation Tool

Clone the repository:
```bash
git clone <repository-url> vlan-automation
cd vlan-automation
```

Set executable permissions:
```bash
chmod +x vlan_manager.py
```

Create required directories:
```bash
mkdir -p logs backups
```

### 4. Configuration Setup

Copy example configuration files:
```bash
cp config/switches.json.example config/switches.json
cp config/vlans.json.example config/vlans.json
```

Edit switch configuration:
```bash
vi config/switches.json
```

Update the following parameters:
- Switch hostnames/IP addresses
- SSH credentials
- Device types and locations

Example switch configuration:
```json
{
    "switches": [
        {
            "name": "core-switch-01",
            "hostname": "192.168.1.10",
            "username": "admin", 
            "password": "your_password",
            "device_type": "cisco_catalyst_2960",
            "location": "Server Room A"
        }
    ]
}
```

### 5. Network Switch Preparation

Ensure switches are configured for SSH access:

```cisco
! Enable SSH on Cisco switch
configure terminal
hostname YourSwitchName
ip domain-name yourdomain.com
crypto key generate rsa general-keys modulus 1024
ip ssh version 2
line vty 0 4
 transport input ssh
 login local
username admin privilege 15 secret your_password
exit
copy running-config startup-config
```

### 6. Test Installation

Test connectivity to switches:
```bash
python vlan_manager.py --config config/switches.json --action inventory
```

Expected output:
```
Switch Inventory Report
=======================
Total switches: 1
Online switches: 1  
Offline switches: 0

Switch Details:
  192.168.1.10 - online (cisco_catalyst_2960)
```

## Usage Examples

### Create VLANs
```bash
python vlan_manager.py --config config/switches.json --vlans config/vlans.json --action create
```

### Check switch inventory
```bash  
python vlan_manager.py --config config/switches.json --action inventory
```

### Target specific switches
```bash
python vlan_manager.py --config config/switches.json --vlans config/vlans.json --action create --switches "192.168.1.10,192.168.1.20"
```

## Troubleshooting

### Common Issues

**SSH Connection Failed**
- Verify SSH service is running on switches
- Check firewall settings
- Confirm credentials are correct
- Test manual SSH connection: `ssh admin@192.168.1.10`

**Permission Denied**
- Ensure user has privilege level 15
- Verify enable password if required
- Check switch AAA configuration

**Python Import Errors**
- Verify Python 2.7 is installed: `python --version`
- Check Paramiko installation: `pip list | grep paramiko`
- Install missing dependencies: `sudo pip install paramiko==1.10.1`

**Configuration Validation Errors**
- Review config files for JSON syntax
- Verify VLAN ID ranges (1-1005, 1006-4094)
- Check interface name formats

### Log Files

Check log files for detailed error information:
```bash
tail -f logs/vlan_automation.log
tail -f logs/vlan_errors.log
```

### Debug Mode

Run with debug logging:
```bash
python vlan_manager.py --config config/switches.json --action inventory
```

Edit lib/logging_system.py to set DEBUG level for verbose output.

## Directory Structure

```
vlan-automation/
├── vlan_manager.py          # Main application
├── lib/                     # Core modules
│   ├── ssh_manager.py       # SSH connection management
│   ├── vlan_parser.py       # VLAN configuration parsing  
│   ├── config_builder.py    # IOS command generation
│   ├── backup_manager.py    # Configuration backups
│   ├── rollback_engine.py   # Rollback functionality
│   ├── validation_module.py # Configuration validation
│   └── logging_system.py    # Audit logging
├── config/                  # Configuration files
│   ├── switches.json        # Switch inventory
│   └── vlans.json          # VLAN configurations
├── logs/                    # Log files
├── backups/                 # Configuration backups
└── README.md               # Project documentation
```

## Security Considerations

### Credential Management
- Store credentials securely
- Use dedicated service accounts
- Rotate passwords regularly
- Consider using SSH keys instead of passwords

### Network Security
- Limit SSH access to management network
- Use VPN for remote access
- Monitor and log all configuration changes
- Implement change approval processes

### Backup Security
- Encrypt backup files
- Store backups in secure location
- Implement backup retention policies
- Test backup restoration procedures

## Support

For technical support:
1. Check log files for error details
2. Review configuration syntax
3. Verify network connectivity
4. Test with single switch first
5. Consult Cisco IOS documentation for switch-specific commands

## Version Compatibility

This tool is designed for:
- Cisco Catalyst 2960 series
- Cisco Catalyst 3560 series  
- Cisco Catalyst 3750 series
- Cisco IOS 12.2 and later
- Python 2.7.x series

For newer equipment or IOS versions, command syntax may need adjustment.