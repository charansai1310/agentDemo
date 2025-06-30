import paramiko

def audit_listening_ports(host, user, password, port=22):
    """Audit listening network ports and services"""
    commands = [
        'ss -tuln',
        'netstat -tuln',
        'ss -tupn | head -15',
        'cat /proc/net/tcp | head -10',
        'cat /proc/net/udp | head -5',
        'cat /proc/net/sockstat'
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