# CheckRunningProcessesAndMemoryUsage.py - PC/Server Audit 5

import paramiko

def audit_processes_memory(host, user, password, port=22):
    """Audit running processes and memory usage"""
    commands = [
        'ps aux --sort=-%mem | head -15',
        'free -h',
        'cat /proc/meminfo | head -10',
        'ps aux --sort=-%cpu | head -10',
        'cat /proc/stat | grep cpu',
        'ps -eo pid,ppid,cmd,%mem,%cpu --sort=-%mem | head -10'
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