# CheckLoggedInUsersAndSessions.py - PC/Server Audit 4

import paramiko

def audit_users_sessions(host, user, password, port=22):
    """Audit logged-in users and active sessions"""
    commands = [
        'who',
        'w',
        'last | head -10',
        'users',
        'ps aux | grep -E "(ssh|login|bash|sh)" | head -10',
        'cat /proc/loadavg'
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