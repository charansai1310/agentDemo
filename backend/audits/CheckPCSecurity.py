# CheckPCSecurity.py - PC Audit 12

import paramiko

def audit_pc_security(host, user, password, port=22):
    """
    PC-specific security posture audit:
    - Endpoint security configuration
    - User activity and access patterns
    - Security-related processes and services
    """
    commands = [
        'ps aux | grep -E "(ssh|bash|login)" | head -10',
        'who',
        'w',
        'last | head -10',
        'cat /etc/passwd | grep -E "(bash|sh)$"',
        'find /home -maxdepth 2 -name ".*" 2>/dev/null | head -10',
        'ps aux --sort=-%cpu | head -10',
        'ss -tuln',
        'cat /proc/version',
        'uptime',
        'cat /etc/ssh/sshd_config | grep -E "(PermitRootLogin|PasswordAuthentication)" 2>/dev/null || echo "SSH config not accessible"',
        'systemctl list-units --type=service --state=running | wc -l'
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