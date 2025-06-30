"""
Generated Audit Script
Audit Name: Network Monitoring
Generated: 2025-06-26 12:31:35
Created by Code Generation Agent
"""

import paramiko
from typing import List, Tuple

def audit_cisco_xr_device(host: str, username: str, password: str, port: int = 22, timeout: int = 30) -> List[Tuple[str, str]]:
    """
    Conduct an audit on a Cisco XR device to assess its configuration, security, and compliance with best practices.
    
    Args:
        host (str): Device hostname or IP address.
        username (str): SSH username.
        password (str): SSH password.
        port (int): SSH port (default: 22).
        timeout (int): Connection timeout in seconds (default: 30).
    
    Returns:
        List[Tuple[str, str]]: List of (command, output) tuples.
    """
    commands = [
        'show hostname',             # Step 2: Retrieve hostname
        'show version',               # Step 2: Retrieve software version
        'show running-config',        # Step 3: Review running configuration
        'show interfaces',            # Step 4: Check interface configuration
        'show access-lists',          # Step 5: Assess security configuration
        'show ip route',              # Step 6: Examine routing configuration
        'show logging'                # Step 7: Analyze system logs
    ]
    
    results = []
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    try:
        client.connect(hostname=host, username=username, password=password, port=port, timeout=timeout)
        
        for command in commands:
            stdin, stdout, stderr = client.exec_command(command)
            # Read outputs, handling both stdout and stderr
            output = stdout.read().decode().strip() or stderr.read().decode().strip()
            results.append((command, output))  # Append command and its output to results
            
    except paramiko.SSHException as e:
        results.append((f"Connection error on {host}:{port}", str(e)))
    except Exception as e:
        results.append((f"Error executing commands on {host}:{port}", str(e)))
    finally:
        client.close()  # Ensure the SSH connection is closed properly
    
    return results  # Return the list of command outputs