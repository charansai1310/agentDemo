# CheckRouterNetworkConfig.py - Router Audit 6

import paramiko

def audit_router_network_config(host, user, password, port=22):
    """
    Router-specific network configuration audit:
    - Routing tables and routes
    - Network interfaces and traffic
    - Network statistics and performance
    """
    commands = [
        'ip route show',
        'ip route show table all',
        'ip addr show',
        'cat /proc/net/route',
        'cat /proc/net/fib_trie | head -20',
        'cat /proc/net/dev',
        'cat /proc/net/netstat',
        'cat /proc/net/snmp | grep -E "(Ip|Icmp|Tcp|Udp)"',
        'ss -s',
        'cat /proc/net/sockstat',
        'ip -s link show',
        'cat /proc/sys/net/ipv4/ip_forward'
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