# CheckRouterSecurity.py - Router Audit 7

import paramiko

def audit_router_security(host, user, password, port=22):
    """
    Router-specific security audit:
    - Network security settings
    - Access controls and filtering
    - Security-related network configuration
    """
    commands = [
        'cat /proc/sys/net/ipv4/ip_forward',
        'cat /proc/sys/net/ipv4/icmp_echo_ignore_all',
        'cat /proc/sys/net/ipv4/icmp_echo_ignore_broadcasts',
        'cat /proc/sys/net/ipv4/tcp_syncookies',
        'cat /proc/sys/net/ipv4/conf/all/accept_redirects',
        'cat /proc/sys/net/ipv4/conf/all/send_redirects',
        'cat /proc/sys/net/ipv4/conf/all/accept_source_route',
        'find /proc/sys/net/ipv4/ -name "*redirect*" -exec echo {} \\; -exec cat {} \\;',
        'ss -tuln | grep -E ":(22|23|80|443|8080)"',
        'cat /proc/net/nf_conntrack | head -10 2>/dev/null || echo "No conntrack"',
        'ls -la /proc/net/ | grep -E "(iptables|netfilter|nf_)"',
        'cat /proc/version'
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