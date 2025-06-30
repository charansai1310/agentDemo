# CheckServerSecurity.py - Server Audit 11

import paramiko

def audit_server_security(host, user, password, port=22):
    """
    Server-specific security baseline audit:
    - Security configuration and hardening
    - Access controls and authentication
    - Security-related services and logs
    """
    commands = [
        'cat /etc/ssh/sshd_config | grep -E "(PermitRootLogin|PasswordAuthentication|Port)"',
        'ss -tuln | grep :22',
        'last | head -10',
        'cat /etc/passwd | wc -l',
        'cat /etc/passwd | grep -E "(bash|sh)$" | wc -l',
        'find /etc -name "*.conf" | head -10',
        'ps aux | grep -E "(ssh|login)" | head -5',
        'cat /proc/version',
        'uname -a',
        'cat /etc/os-release 2>/dev/null || cat /etc/issue',
        'systemctl list-units --type=service --state=running | grep -E "(ssh|security|auth)" || echo "No security services found"',
        'find /var/log -name "*.log" -type f | head -5'
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