# CheckSwitchMAC.py - Switch Audit 9

import paramiko

def audit_switch_mac(host, user, password, port=22):
    """
    Switch-specific MAC address and learning audit:
    - ARP tables and neighbor discovery
    - Network topology and connectivity
    - MAC address learning and caching
    """
    commands = [
        'ip neigh show',
        'arp -a',
        'cat /proc/net/arp',
        'ip link show | grep -E "(link/ether|link/loopback)"',
        'cat /sys/class/net/*/address 2>/dev/null',
        'for iface in $(ls /sys/class/net/); do echo "=== $iface MAC ==="; cat /sys/class/net/$iface/address 2>/dev/null; done',
        'ss -tuln | wc -l',
        'cat /proc/net/dev_mcast',
        'cat /proc/net/igmp',
        'cat /proc/net/packet',
        'netstat -i',
        'ip maddr show 2>/dev/null || echo "No multicast addrs"'
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