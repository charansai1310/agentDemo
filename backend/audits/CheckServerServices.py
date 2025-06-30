# CheckServerServices.py - Server Audit 10

import paramiko

def audit_server_services(host, user, password, port=22):
    """
    Server-specific service monitoring audit:
    - System services and daemons
    - Service status and health
    - Resource utilization by services
    """
    commands = [
        'systemctl list-units --type=service --state=running',
        'systemctl list-units --type=service --state=failed',
        'ps aux | grep -E "(daemon|service)" | head -10',
        'ps aux --sort=-%mem | head -15',
        'ss -tuln | grep -E ":(80|443|22|21|25|53|3306|5432)"',
        'systemctl status sshd',
        'cat /proc/loadavg',
        'uptime',
        'who',
        'ps -ef | wc -l',
        'cat /proc/meminfo | grep -E "(MemTotal|MemFree|Buffers|Cached)"',
        'df -h'
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