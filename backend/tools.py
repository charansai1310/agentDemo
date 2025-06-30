"""
Database tools and audit execution functions for the Audit Management System
Contains core database connectivity, data retrieval, and audit execution on containers
Updated to use direct database queries for retrieval operations
"""
import re
import os
import sys
import importlib.util
import inspect
import time
import ast
from datetime import datetime
from typing import Optional, List, Dict, Tuple
from pathlib import Path

from config import CODE_GENERATION_AGENT_TOPIC, DATABASE_CONFIG
from config import (
    ORCHESTRATOR_AGENT_TOPIC,
    AUDIT_RETRIEVAL_AGENT_TOPIC,
    EXECUTE_AUDIT_AGENT_TOPIC,
    ENGINEER_AGENT_TOPIC,
    USER_TOPIC
)

# Import database functions
from database import get_cached_data, refresh_all_data, get_database_connection

# SSH Connection Constants
SSH_USERNAME = "root"
SSH_PASSWORD = "rootpassword"
SSH_HOST = "localhost"
SSH_TIMEOUT = 30

async def get_db_connection():
    """Legacy async wrapper for compatibility - but we'll use sync psycopg2"""
    return get_database_connection()

# Transfer functions for agent delegation
def transfer_to_audit_retrieval() -> str:
    """Transfer control to audit retrieval agent"""
    return AUDIT_RETRIEVAL_AGENT_TOPIC

def transfer_to_audit_execution() -> str:
    """Transfer control to audit execution agent"""
    return EXECUTE_AUDIT_AGENT_TOPIC

def transfer_to_engineer() -> str:
    """Transfer control to engineer agent for custom audit creation"""
    return ENGINEER_AGENT_TOPIC

def transfer_to_code_generator() -> str:
    """Transfer control to code generation agent"""
    return CODE_GENERATION_AGENT_TOPIC

# Cache wrapper functions for execution - Updated to use direct database queries
def is_cache_empty() -> bool:
    """Check if audit database has any records"""
    conn = get_database_connection()
    if not conn:
        return True
    
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM audits")
        count = cursor.fetchone()[0]
        return count == 0
        
    except Exception as e:
        print(f"Error checking audit count: {e}")
        return True
    finally:
        if cursor:
            cursor.close()
        conn.close()

def get_cache() -> List[Dict]:
    """Get audits from database in execution format"""
    conn = get_database_connection()
    if not conn:
        return []
    
    cursor = None
    try:
        cursor = conn.cursor()
        query = """
            SELECT audit_id, audit_name, category, description
            FROM audits 
            ORDER BY audit_id
        """
        cursor.execute(query)
        results = cursor.fetchall()
        
        cache_list = []
        for idx, row in enumerate(results, 1):
            cache_list.append({
                'index': idx,
                'audit_id': str(row[0]),
                'audit_name': row[1],
                'audit_category': row[2],
                'description': row[3] if row[3] else 'No description available'
            })
        return cache_list
        
    except Exception as e:
        print(f"Error getting audits from database: {e}")
        return []
    finally:
        if cursor:
            cursor.close()
        conn.close()

def find_audit_in_cache(identifier: str) -> Optional[Dict]:
    """Find audit in database by identifier"""
    conn = get_database_connection()
    if not conn:
        return None
    
    cursor = None
    try:
        cursor = conn.cursor()
        
        # Try as index number first - get all audits ordered by ID
        if identifier.isdigit():
            query = """
                SELECT audit_id, audit_name, category, description
                FROM audits 
                ORDER BY audit_id
                LIMIT 1 OFFSET %s
            """
            index = int(identifier) - 1  # Convert to 0-based index
            cursor.execute(query, (index,))
            result = cursor.fetchone()
            
            if result:
                return {
                    'index': int(identifier),
                    'audit_id': str(result[0]),
                    'audit_name': result[1],
                    'audit_category': result[2],
                    'audit_path': get_audit_file_path(str(result[0])),
                    'description': result[3] if result[3] else 'No description available'
                }
        
        # Try as audit ID
        query = """
            SELECT audit_id, audit_name, category, description
            FROM audits 
            WHERE audit_id = %s
        """
        cursor.execute(query, (identifier,))
        result = cursor.fetchone()
        
        if result:
            # Get index by counting audits with smaller IDs
            cursor.execute("SELECT COUNT(*) FROM audits WHERE audit_id < %s", (result[0],))
            index = cursor.fetchone()[0] + 1
            
            return {
                'index': index,
                'audit_id': str(result[0]),
                'audit_name': result[1],
                'audit_category': result[2],
                'audit_path': get_audit_file_path(str(result[0])),
                'description': result[3] if result[3] else 'No description available'
            }
        
        # Try as audit name (exact match)
        query = """
            SELECT audit_id, audit_name, category, description
            FROM audits 
            WHERE LOWER(audit_name) = LOWER(%s)
        """
        cursor.execute(query, (identifier,))
        result = cursor.fetchone()
        
        if result:
            # Get index by counting audits with smaller IDs
            cursor.execute("SELECT COUNT(*) FROM audits WHERE audit_id < %s", (result[0],))
            index = cursor.fetchone()[0] + 1
            
            return {
                'index': index,
                'audit_id': str(result[0]),
                'audit_name': result[1],
                'audit_category': result[2],
                'audit_path': get_audit_file_path(str(result[0])),
                'description': result[3] if result[3] else 'No description available'
            }
        
        # Try as partial audit name match
        query = """
            SELECT audit_id, audit_name, category, description
            FROM audits 
            WHERE LOWER(audit_name) LIKE LOWER(%s)
            LIMIT 1
        """
        cursor.execute(query, (f'%{identifier}%',))
        result = cursor.fetchone()
        
        if result:
            # Get index by counting audits with smaller IDs
            cursor.execute("SELECT COUNT(*) FROM audits WHERE audit_id < %s", (result[0],))
            index = cursor.fetchone()[0] + 1
            
            return {
                'index': index,
                'audit_id': str(result[0]),
                'audit_name': result[1],
                'audit_category': result[2],
                'audit_path': get_audit_file_path(str(result[0])),
                'description': result[3] if result[3] else 'No description available'
            }
        
        return None
        
    except Exception as e:
        print(f"Error finding audit in database: {e}")
        return None
    finally:
        if cursor:
            cursor.close()
        conn.close()

def get_audit_file_path(audit_id: str) -> str:
    """Get audit file path from database"""
    conn = get_database_connection()
    if not conn:
        return f"./audits/audit_{audit_id}.py"  # Fallback path
    
    cursor = None
    try:
        cursor = conn.cursor()
        # You can correct this query to match your actual schema
        cursor.execute("SELECT audit_path FROM audits WHERE audit_id = %s", (audit_id,))
        result = cursor.fetchone()
        
        if result and result[0]:
            return result[0]
        else:
            # Fallback: construct path from audit name
            cursor.execute("SELECT audit_name FROM audits WHERE audit_id = %s", (audit_id,))
            name_result = cursor.fetchone()
            if name_result:
                safe_name = re.sub(r'[^\w\s-]', '_', name_result[0])
                return f"./audits/{safe_name.replace(' ', '_')}.py"
            else:
                return f"./audits/audit_{audit_id}.py"
    
    except Exception as e:
        print(f"Error getting audit file path: {e}")
        return f"./audits/audit_{audit_id}.py"  # Fallback
    finally:
        if cursor:
            cursor.close()
        conn.close()

# Audit Execution Functions
async def execute_audit_by_identifier(identifier: str) -> str:
    """Execute audit by identifier using database queries"""
    
    # Check if database has audits
    if is_cache_empty():
        return "No audits available in database. Please check the system data."
    
    # Find audit in database
    audit = find_audit_in_cache(identifier)
    
    if not audit:
        # Show available options from database
        cache = get_cache()
        options = "Available audits:\n"
        for cached_audit in cache:
            options += f"{cached_audit['index']}. {cached_audit['audit_name']}\n"
        return f"Audit '{identifier}' not found.\n\n{options}\nPlease select an audit by number or name."
    
    # Get compatible devices from database
    devices = get_compatible_devices_from_cache(audit['audit_id'])
    
    if not devices:
        return f"No compatible devices found for audit '{audit['audit_name']}'"
    
    print(f"\nExecuting audit '{audit['audit_name']}' on {len(devices)} compatible devices...")
    
    # Execute audit on each compatible device
    results = []
    successful_executions = 0
    failed_executions = 0
    device_not_responding = 0
    
    for device in devices:
        status, results_content, duration, error_message = await execute_audit_on_device(
            audit['audit_path'], 
            audit['audit_name'], 
            device
        )
        
        # Generate summary based on status
        if status == "success":
            summary = f"Audit completed successfully in {duration:.2f} seconds"
            successful_executions += 1
        elif status == "device_not_responding":
            summary = f"Device not responding on port {device['port']}"
            device_not_responding += 1
        else:
            summary = f"Audit failed: {error_message}"
            failed_executions += 1
        
        # Store report in database (direct DB storage)
        report_id = store_report_in_db_sync(
            audit['audit_id'], 
            device['device_id'], 
            audit['audit_name'], 
            device['device_name'],
            status, 
            results_content, 
            summary, 
            error_message, 
            duration
        )
        
        results.append({
            'device': device['device_name'],
            'status': status,
            'duration': duration,
            'report_id': report_id
        })
        
        print(f"  - {device['device_name']}: {status} ({duration:.2f}s)")
    
    # Generate final summary
    total_devices = len(devices)
    summary_report = f"\nAUDIT EXECUTION SUMMARY\n"
    summary_report += f"{'=' * 50}\n"
    summary_report += f"Audit: {audit['audit_name']}\n"
    summary_report += f"Total Devices: {total_devices}\n"
    summary_report += f"Successful: {successful_executions}\n"
    summary_report += f"Failed: {failed_executions}\n"
    summary_report += f"Not Responding: {device_not_responding}\n"
    summary_report += f"{'=' * 50}\n\n"
    
    summary_report += "DEVICE RESULTS:\n"
    for result in results:
        summary_report += f"• {result['device']}: {result['status']} - {result['duration']:.2f}s\n"
    
    summary_report += f"\nAll audit results stored in reports table."
    
    return summary_report

def get_compatible_devices_from_cache(audit_id: str) -> List[Dict]:
    """Get compatible devices for audit from database"""
    conn = get_database_connection()
    if not conn:
        return []
    
    cursor = None
    try:
        cursor = conn.cursor()
        
        # First get the audit's compatible device categories
        query = """
            SELECT device_categories
            FROM audits 
            WHERE audit_id = %s
        """
        cursor.execute(query, (audit_id,))
        result = cursor.fetchone()
        
        if not result or not result[0]:
            return []
        
        # Parse compatible categories
        compatible_categories = [cat.strip() for cat in result[0].split(',')]
        
        # Get devices that match these categories
        if compatible_categories:
            placeholders = ','.join(['%s'] * len(compatible_categories))
            query = f"""
                SELECT device_id, device_name, category, port
                FROM devices 
                WHERE category IN ({placeholders})
                ORDER BY device_id
            """
            cursor.execute(query, compatible_categories)
            results = cursor.fetchall()
            
            compatible_devices = []
            for row in results:
                port = 22  # Default port
                if row[3]:  # If port column exists and has value
                    port_str = str(row[3])
                    # Handle format like "2221:22"
                    if ':' in port_str:
                        port = int(port_str.split(':')[0])
                    else:
                        port = int(port_str)
                
                compatible_devices.append({
                    'device_id': str(row[0]),
                    'device_name': row[1],
                    'category': row[2],
                    'port': port
                })
            
            return compatible_devices
        
        return []
        
    except Exception as e:
        print(f"Error getting compatible devices from database: {e}")
        return []
    finally:
        if cursor:
            cursor.close()
        conn.close()

def get_device_port(device_id: str) -> int:
    """Get device port from database"""
    conn = get_database_connection()
    if not conn:
        return 22  # Default SSH port
    
    cursor = None
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT port FROM devices WHERE device_id = %s", (device_id,))
        result = cursor.fetchone()
        
        if result and result[0]:
            port_str = str(result[0])
            # Handle format like "2221:22"
            if ':' in port_str:
                return int(port_str.split(':')[0])
            else:
                return int(port_str)
        else:
            return 22  # Default
    
    except Exception as e:
        print(f"Error getting device port: {e}")
        return 22
    finally:
        if cursor:
            cursor.close()
        conn.close()

async def execute_audit_on_device(audit_path: str, audit_name: str, device: Dict) -> Tuple[str, str, float, str]:
    """Execute audit on a specific device"""
    start_time = time.time()
    
    try:
        # Debug info
        print(f"  🔍 Executing on device: {device['device_name']} (port: {device['port']})")
        
        # Check if audit file exists
        if not os.path.exists(audit_path):
            raise Exception(f"Audit file not found: {audit_path}")
        
        # Import the audit module
        audit_file_name = Path(audit_path).stem
        spec = importlib.util.spec_from_file_location(audit_file_name, audit_path)
        if spec is None or spec.loader is None:
            raise Exception(f"Could not load audit module from '{audit_path}'")
        
        audit_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(audit_module)
        
        # Find the main audit function
        audit_functions = [attr for attr in dir(audit_module) 
                          if callable(getattr(audit_module, attr)) and 
                          attr.startswith('audit_')]
        
        if not audit_functions:
            raise Exception(f"No audit functions found in '{audit_path}'")
        
        audit_function = getattr(audit_module, audit_functions[0])
        print(f"  🔧 Found audit function: {audit_functions[0]}")
        
        # Check function signature and call with appropriate parameters
        sig = inspect.signature(audit_function)
        params = list(sig.parameters.keys())
        
        # Call the audit function
        if 'port' in params:
            result = audit_function(SSH_HOST, SSH_USERNAME, SSH_PASSWORD, device['port'])
        else:
            result = audit_function(SSH_HOST, SSH_USERNAME, SSH_PASSWORD)
        
        # Format results as text content
        results_content = f"AUDIT: {audit_name}\n"
        results_content += f"DEVICE: {device['device_name']} ({device['category']})\n"
        results_content += f"EXECUTION TIME: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        results_content += f"{'=' * 50}\n\n"
        
        if result:
            for i, (command, output) in enumerate(result, 1):
                results_content += f"{i}. Command: {command}\n"
                results_content += f"Output:\n{output}\n"
                results_content += f"{'-' * 30}\n"
        else:
            results_content += "No results returned from audit execution.\n"
        
        duration = time.time() - start_time
        return "success", results_content, duration, ""
        
    except Exception as e:
        duration = time.time() - start_time
        error_msg = str(e)
        
        # Check if it's a connection error
        if "Connection refused" in error_msg or "timeout" in error_msg.lower():
            return "device_not_responding", "", duration, error_msg
        else:
            return "failed", "", duration, error_msg

def store_report_in_db_sync(audit_id: str, device_id: str, audit_name: str, device_name: str, 
                           status: str, results_content: str, summary: str, error_message: str, 
                           duration: float) -> Optional[int]:
    """Store audit execution report in database (sync)"""
    conn = get_database_connection()
    if not conn:
        return None
    
    cursor = None
    try:
        cursor = conn.cursor()
        # Adjusted query to match your actual reports table schema (removed duration column)
        cursor.execute("""
            INSERT INTO reports (audit_id, device_id, audit_name, device_name, status, results, summary, error_message, execution_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING report_id
        """, (audit_id, device_id, audit_name, device_name, status, results_content, summary, error_message, datetime.now()))
        
        report_id = cursor.fetchone()[0]
        conn.commit()
        return report_id
    
    except Exception as e:
        print(f"Error storing report: {e}")
        conn.rollback()
        return None
    finally:
        if cursor:
            cursor.close()
        conn.close()

# Legacy compatibility functions - Updated to use database queries
async def get_audit_details() -> str:
    """Get audit details from database"""
    conn = get_database_connection()
    if not conn:
        return "Error connecting to database."
    
    cursor = None
    try:
        cursor = conn.cursor()
        
        query = """
            SELECT audit_id, audit_name, category, description
            FROM audits 
            ORDER BY audit_id
        """
        cursor.execute(query)
        results = cursor.fetchall()
        
        if not results:
            return "No audits found in database."
        
        audit_list = f"Available Audits ({len(results)} total)\n\n"
        
        for idx, row in enumerate(results, 1):
            audit_list += f"{idx}. {row[1]}\n"
            audit_list += f"ID: {row[0]}\n"
            audit_list += f"Category: {row[2]}\n"
            
            if row[3]:
                description = row[3]
                if len(description) > 100:
                    description = description[:100] + "..."
                audit_list += f"Description: {description}\n"
            
            audit_list += "\n"
        
        return audit_list.strip()
        
    except Exception as e:
        print(f"Error getting audit details from database: {e}")
        return f"Error retrieving audit details: {e}"
    finally:
        if cursor:
            cursor.close()
        conn.close()

async def get_compatible_devices(audit_id: int) -> List[Dict]:
    """Legacy function - use get_compatible_devices_from_cache instead"""
    return get_compatible_devices_from_cache(str(audit_id))

async def store_report_in_db(audit_id: int, device_id: int, audit_name: str, device_name: str, 
                           status: str, results_content: str, summary: str, error_message: str, 
                           duration: float) -> Optional[int]:
    """Legacy async wrapper for store_report_in_db_sync"""
    return store_report_in_db_sync(str(audit_id), str(device_id), audit_name, device_name, 
                                  status, results_content, summary, error_message, duration)

# Code Generation Functions (needed by CodeGenerationAgent)

def load_existing_audit_templates() -> List[Dict[str, str]]:
    """
    Load existing audit files as templates for code generation
    
    Returns:
        List[Dict]: List of audit templates with name and content
    """
    templates = []
    audits_dir = Path("./audits")
    
    if not audits_dir.exists():
        print(f"Audits directory not found: {audits_dir}")
        return create_fallback_audit_templates()
    
    try:
        python_files = list(audits_dir.glob("*.py"))
        if not python_files:
            print("No Python audit files found in audits directory")
            return create_fallback_audit_templates()
        
        for audit_file in python_files:
            if audit_file.name != "__init__.py":
                try:
                    with open(audit_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    templates.append({
                        'name': audit_file.stem,
                        'filename': audit_file.name,
                        'content': content,
                        'description': extract_audit_description(content)
                    })
                    
                    print(f"Loaded audit template: {audit_file.name}")
                    
                except Exception as e:
                    print(f"Error reading audit template {audit_file}: {e}")
    
    except Exception as e:
        print(f"Error loading audit templates: {e}")
        return create_fallback_audit_templates()
    
    return templates

def extract_audit_description(code_content: str) -> str:
    """Extract description from audit code docstring or comments"""
    try:
        # Look for function docstrings
        lines = code_content.split('\n')
        in_docstring = False
        docstring_lines = []
        
        for line in lines:
            stripped = line.strip()
            if '"""' in stripped and not in_docstring:
                in_docstring = True
                # Get content after opening """
                after_quotes = stripped.split('"""', 1)[1] if stripped.split('"""', 1)[1] else ""
                if after_quotes:
                    docstring_lines.append(after_quotes)
                continue
            elif '"""' in stripped and in_docstring:
                # Get content before closing """
                before_quotes = stripped.split('"""')[0]
                if before_quotes:
                    docstring_lines.append(before_quotes)
                break
            elif in_docstring:
                # Clean up the docstring line
                clean_line = stripped.lstrip('- *').strip()
                if clean_line:
                    docstring_lines.append(clean_line)
        
        if docstring_lines:
            description = ' '.join(docstring_lines)
            return description[:300] + "..." if len(description) > 300 else description
    except:
        pass
    
    # Fallback to comments at the top
    lines = code_content.split('\n')
    description_lines = []
    for line in lines[:15]:
        stripped = line.strip()
        if stripped.startswith('#') and not stripped.startswith('#!/'):
            clean_comment = stripped.lstrip('#').strip()
            if clean_comment and not clean_comment.startswith('-'):
                description_lines.append(clean_comment)
        elif description_lines and stripped and not stripped.startswith('#'):
            break
    
    if description_lines:
        description = ' '.join(description_lines)
        return description[:300] + "..." if len(description) > 300 else description
    
    return "Network audit function"

def create_fallback_audit_templates() -> List[Dict[str, str]]:
    """Create fallback audit templates based on actual audit files"""
    fallback_templates = [
        {
            'name': 'CheckRouterSecurity',
            'filename': 'CheckRouterSecurity.py',
            'content': '''# CheckRouterSecurity.py - Router Audit

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
        'ss -tuln | grep -E ":(22|23|80|443|8080)"',
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
''',
            'description': 'Router-specific security audit for network security settings, access controls and filtering'
        },
        {
            'name': 'CheckServerServices',
            'filename': 'CheckServerServices.py',
            'content': '''# CheckServerServices.py - Server Audit

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
        'ps aux --sort=-%mem | head -15',
        'ss -tuln | grep -E ":(80|443|22|21|25|53)"',
        'cat /proc/loadavg',
        'uptime',
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
''',
            'description': 'Server-specific service monitoring audit for system services and daemons'
        }
    ]
    
    return fallback_templates

def validate_python_code(code: str) -> Tuple[bool, str]:
    """
    Validate Python code syntax and basic structure
    
    Args:
        code: Python code string
        
    Returns:
        Tuple[bool, str]: (is_valid, error_message)
    """
    try:
        # Check syntax
        ast.parse(code)
        
        # Check for required function
        tree = ast.parse(code)
        functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        audit_functions = [f for f in functions if f.startswith('audit_')]
        
        if not audit_functions:
            return False, "No audit function found (function name should start with 'audit_')"
        
        # Check for basic imports
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        
        required_imports = ['paramiko']
        missing_imports = [imp for imp in required_imports if imp not in imports]
        
        if missing_imports:
            return False, f"Missing required imports: {', '.join(missing_imports)}"
        
        return True, "Code validation passed"
        
    except SyntaxError as e:
        return False, f"Syntax error: {e}"
    except Exception as e:
        return False, f"Validation error: {e}"

def save_generated_audit(code: str, filename: str) -> Tuple[bool, str]:
    """
    Save generated audit code to file
    
    Args:
        code: Generated Python code
        filename: Original MOP filename (will be converted to .py)
        
    Returns:
        Tuple[bool, str]: (success, file_path_or_error)
    """
    try:
        # Ensure generated_audits directory exists
        output_dir = Path("./generated_audits")
        output_dir.mkdir(exist_ok=True)
        
        # Convert filename to Python file
        base_name = Path(filename).stem
        # Clean filename for Python module
        clean_name = re.sub(r'[^\w\s-]', '_', base_name.lower())
        py_filename = f"{clean_name}_audit.py"
        
        output_path = output_dir / py_filename
        
        # Add header comment
        header = f'''"""
Generated Audit Script
Source MOP: {filename}
Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}
Based on existing audit patterns in the system
"""

'''
        
        full_code = header + code
        
        # Save file
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(full_code)
        
        return True, str(output_path.absolute())
        
    except Exception as e:
        return False, f"Error saving file: {e}"

def get_mop_filename_from_path(file_path: str) -> str:
    """Extract filename from MOP file path"""
    return Path(file_path).name

# Tool collections for each agent
ORCHESTRATOR_TOOLS = [
    "transfer_to_audit_retrieval",
    "transfer_to_audit_execution",
    "transfer_to_engineer",
    "transfer_to_code_generator"
]

CODE_GENERATION_AGENT_TOOLS = [
    "load_existing_audit_templates",
    "validate_python_code", 
    "save_generated_audit",
    "get_mop_filename_from_path"
]

ENGINEER_AGENT_TOOLS = [
    "transfer_to_code_generator"
]

EXECUTE_AUDIT_AGENT_TOOLS = [
    "execute_audit_by_identifier",
    "get_compatible_devices",
    "execute_audit_on_device",
    "store_report_in_db",
    "get_audit_details"
]