"""
Generated Audit Script
Audit Name: Cisco Devices Security
Generated: 2025-06-25 10:56:15
Created by Code Generation Agent
"""

import paramiko
from typing import List, Tuple

def audit_switch_interface_status(host, username, password, port=22, timeout=30):
    """
    Audit script to check the interface status of a network switch:
    - Retrieve the status of all interfaces
    - Check for errors and dropped packets
    - Verify link status and statistics
    
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
        'show interfaces status',  # Interface status and link status
        'show interfaces counters',  # Interfaces statistics including errors and dropped packets
        'show ip interface brief',  # Summary information about the interfaces
        'show run | section interface'  # Check configurations for interfaces
    ]
    
    results = []
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(hostname=host, username=username, password=password, port=port, timeout=timeout)
        
        for command in commands:
            stdin, stdout, stderr = client.exec_command(command)
            output = stdout.read().decode().strip() or stderr.read().decode().strip()
            results.append((command, output))
    
    except Exception as e:
        results.append((f"Connection error: {host}:{port}", str(e)))
    
    finally:
        client.close()
    
    return results