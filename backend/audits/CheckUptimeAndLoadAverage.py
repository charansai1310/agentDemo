# CheckUptimeAndLoadAverage.py - Universal Audit 2

import paramiko

def audit_uptime_load(host, user, password, port=22):
    """Audit system uptime and load average"""
    commands = [
        'uptime',
        'cat /proc/loadavg',
        'cat /proc/stat | head -1',
        'cat /proc/meminfo | grep -E "(MemTotal|MemFree|MemAvailable)"'
    ]
    return run_audit(host, user, password, commands, port)

def run_audit(host, user, password, commands, port=22):
    results = []
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(hostname=host, username=user, password=password, port=port, timeout=30)
        
        for cmd in commands:
            stdin, stdout, stderr = client.exec_command(cmd)
            output = stdout.read().decode().strip()
            results.append((cmd, output))
        
        client.close()
        return results
    except Exception as e:
        print(f"Error on {host}:{port}: {e}")
        return []