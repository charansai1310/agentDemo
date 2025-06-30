"""
Generated Audit Script
Audit Name: Cisco XoR Audit
Generated: 2025-06-24 14:12:53
Created by Code Generation Agent
"""

import paramiko
from typing import List, Tuple

def audit_cisco_xr_device(host, username, password, port=22, timeout=30):
    """
    Audit script for Cisco XR devices:
    - Check system status and configuration
    - Verify interface configurations and status
    - Examine routing protocols and their status
    - Retrieve logging and error information
    
    Args:
        host (str): Device hostname or IP address
        username (str): SSH username
        password (str): SSH password  
        port (int): SSH port (default: 22)
        timeout (int): Connection timeout in seconds (default: 30)
    
    Returns:
        List[Tuple[str, str]]: List of (command, output) tuples
    """
    commands = [
        'show version',
        'show interfaces',
        'show ip route',
        'show logging',
        'show running-config',
        'show ipv6 interface'
    ]
    return run_audit(host, username, password, commands, port, timeout)

def run_audit(host, username, password, commands, port=22, timeout=30):
    results = []
    client = paramiko.SSHClient()
    try:
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=host, username=username, password=password, port=port, timeout=timeout)
        
        for command in commands:
            stdin, stdout, stderr = client.exec_command(command)
            output = stdout.read().decode().strip()
            error_output = stderr.read().decode().strip()
            
            if output:  # If there is a valid command output
                results.append((command, output))
            elif error_output:  # If there was an error returned
                results.append((command, f"Error: {error_output}"))
            else:  # No output or error
                results.append((command, "No output returned"))
    
    except Exception as e:
        results.append(("Connection Error", str(e)))
    finally:
        client.close()
    
    return results