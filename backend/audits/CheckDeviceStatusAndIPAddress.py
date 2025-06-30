# CheckDeviceStatusAndIPAddress.py - Universal Audit 1
import paramiko

def audit_device_status_ip(host, user, password, port=22):
    """Comprehensive device audit for status, IP, and connectivity"""
    commands = [
        'uname -a',
        'uptime',
        'date',
        'ip -o -4 addr show',
        'ip route show',
        'hostname -I',
        'ss -tuln',
        'ss -tun | head -10',
        'ip neigh show',
        'ps aux | head -10',
        'df -h',
        'free -h',
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