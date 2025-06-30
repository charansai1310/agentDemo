# CheckSwitchPorts.py - Switch Audit 8

import paramiko

def audit_switch_ports(host, user, password, port=22):
    """
    Switch-specific port and interface audit:
    - Interface status and statistics
    - Network bridging and switching
    - Port utilization and errors
    """
    commands = [
        'ip link show',
        'ip -s link show',
        'cat /proc/net/dev',
        'cat /sys/class/net/*/statistics/rx_bytes 2>/dev/null | head -10',
        'cat /sys/class/net/*/statistics/tx_bytes 2>/dev/null | head -10',
        'cat /sys/class/net/*/statistics/rx_errors 2>/dev/null | head -10',
        'cat /sys/class/net/*/statistics/tx_errors 2>/dev/null | head -10',
        'ls /sys/class/net/',
        'for iface in $(ls /sys/class/net/); do echo "=== $iface ==="; cat /sys/class/net/$iface/operstate 2>/dev/null; done',
        'cat /proc/net/bonding_masters 2>/dev/null || echo "No bonding"',
        'cat /proc/net/vlan/* 2>/dev/null || echo "No VLAN config"',
        'ss -i | head -20'
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