"""
Generated Audit Script
Audit Name: cisco
Generated: 2025-06-24 14:17:40
Created by Code Generation Agent
"""

def audit_cisco_device(host, username, password, port=22, timeout=30):
    """
    Audit specific Cisco device configurations and statuses:
    - Check running configuration
    - Check interface statuses
    - Check routing protocols
    - Check active sessions
    
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
        'show running-config',
        'show ip interface brief',
        'show ip route',
        'show users'
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
            results.append((command, output))
    except Exception as e:
        print(f"Error connecting to {host}:{port} - {e}")
        return []
    finally:
        client.close()
    
    return results