"""
PostgreSQL database connection and in-memory data caching for the Audit Management System
Simple database operations without triggers or notifications
"""

import psycopg2
import json
import logging
from datetime import datetime
from typing import Dict, List, Any, Optional
from config import DATABASE_CONFIG

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Global in-memory cache for all data
_cached_data = None
_cache_timestamp = None

# Hardcoded audit aliases (configuration data)
audit_aliases = {
    "Check Device Status and IP Address": [
        "device status",
        "IP address check", 
        "status and IP audit",
        "device info"
    ],
    "Check Uptime and Load Average": [
        "uptime check",
        "load average audit",
        "system load",
        "uptime and performance"
    ],
    "Check Listening Ports": [
        "open ports",
        "port check",
        "listening ports audit",
        "active ports"
    ],
    "Check Logged in Users and Sessions": [
        "logged-in users",
        "user sessions",
        "login audit",
        "current sessions"
    ],
    "Check Running Processes and Memory Usage": [
        "process check",
        "memory usage",
        "running processes",
        "CPU and memory audit"
    ],
    "PC Security Posture": [
        "PC security check",
        "endpoint posture",
        "device hardening audit",
        "security posture assessment"
    ],
    "Server Security Baseline": [
        "server baseline",
        "security baseline",
        "server audit",
        "system hardening check"
    ],
    "Switch MAC Table": [
        "mac address table",
        "switch MAC audit",
        "MAC table check",
        "learned MACs"
    ],
    "Switch Port Status": [
        "port status",
        "switch port check",
        "interface status",
        "switch interface audit"
    ],
    "Router Network Config": [
        "router config",
        "network config check",
        "router setup",
        "routing configuration"
    ],
    "Router Security Audit": [
        "router security",
        "router hardening audit",
        "network security check",
        "router vulnerability scan"
    ],
    "Server Services Audit": [
        "server services",
        "running services check",
        "service audit",
        "server process status"
    ]
}

def get_database_connection():
    """Get a connection to the PostgreSQL database with proper error handling"""
    try:
        connection = psycopg2.connect(**DATABASE_CONFIG)
        connection.autocommit = False  # Explicit transaction control
        return connection
    except psycopg2.OperationalError as e:
        logger.error(f"PostgreSQL Operational Error: {e}")
        return None
    except psycopg2.Error as e:
        logger.error(f"PostgreSQL Error: {e}")
        return None
    except Exception as e:
        logger.error(f"General Database Error: {e}")
        return None

def load_audits_data_from_db() -> List[Dict[str, Any]]:
    """Load all audits data from database"""
    conn = get_database_connection()
    if not conn:
        logger.warning("Cannot connect to database to load audits")
        return []
    
    cursor = None
    try:
        cursor = conn.cursor()
        
        query = """
            SELECT audit_id, audit_name, category, tags, description, device_categories
            FROM audits 
            ORDER BY audit_id;
        """
        cursor.execute(query)
        results = cursor.fetchall()
        
        audits = []
        for row in results:
            audit = {
                "audit_id": str(row[0]),
                "audit_name": row[1],
                "audit_category": row[2],
                "audit_tags": row[3],
                "description": row[4],
                "device_categories": row[5].split(',') if row[5] else []
            }
            audits.append(audit)

        return audits
    
    except Exception as e:
        logger.error(f"Error loading audits data: {e}")
        return []
    finally:
        if cursor:
            cursor.close()
        conn.close()

def load_devices_data_from_db() -> List[Dict[str, Any]]:
    """Load all devices data from database"""
    conn = get_database_connection()
    if not conn:
        logger.warning("Cannot connect to database to load devices")
        return []
    
    cursor = None
    try:
        cursor = conn.cursor()
        
        query = """
            SELECT device_id, device_name, category
            FROM devices 
            ORDER BY device_id;
        """
        cursor.execute(query)
        results = cursor.fetchall()
        
        devices = []
        for row in results:
            device = {
                "device_id": str(row[0]),
                "device_name": row[1],
                "device_category": row[2]
            }
            devices.append(device)

        return devices
    
    except Exception as e:
        logger.error(f"Error loading devices data: {e}")
        return []
    finally:
        if cursor:
            cursor.close()
        conn.close()

def load_reports_data_from_db() -> List[Dict[str, Any]]:
    """Load all reports data from database"""
    conn = get_database_connection()
    if not conn:
        logger.warning("Cannot connect to database to load reports")
        return []
    
    cursor = None
    try:
        cursor = conn.cursor()
        
        query = """
            SELECT report_id, audit_id, device_id, audit_name, device_name, 
                   execution_time, status, results
            FROM reports 
            ORDER BY execution_time DESC;
        """
        cursor.execute(query)
        results = cursor.fetchall()
        
        reports = []
        for row in results:
            report = {
                "report_id": str(row[0]),
                "audit_id": str(row[1]),
                "device_id": str(row[2]),
                "audit_name": row[3],
                "device_name": row[4],
                "execution_time": row[5].isoformat() if row[5] else None,
                "status": row[6],
                "results": row[7]
            }
            reports.append(report)
        
        return reports
    
    except Exception as e:
        logger.error(f"Error loading reports data: {e}")
        return []
    finally:
        if cursor:
            cursor.close()
        conn.close()

def generate_audit_device_compatibility(audits_data: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    """Generate audit device compatibility mapping from database data"""
    compatibility = {}
    
    for audit in audits_data:
        audit_name = audit["audit_name"]
        device_categories = audit["device_categories"]
        compatibility[audit_name] = device_categories
    
    return compatibility

def refresh_all_data() -> Dict[str, Any]:
    """
    Load all data from database and store in memory
    This method will be called from main.py on system startup
    """
    global _cached_data, _cache_timestamp
    
    # Load data from all tables
    audits_data = load_audits_data_from_db()
    devices_data = load_devices_data_from_db()
    reports_data = load_reports_data_from_db()
    
    # Extract lists for easy access (same format as your hardcoded lists)
    audit_names = [audit["audit_name"] for audit in audits_data]
    audit_ids = [audit["audit_id"] for audit in audits_data]
    audit_categories = list(set([audit["audit_category"] for audit in audits_data]))
    
    device_names = [device["device_name"] for device in devices_data]
    device_categories = list(set([device["device_category"] for device in devices_data]))
    
    # Generate audit device compatibility from database
    audit_device_compatibility = generate_audit_device_compatibility(audits_data)
    
    # Structure all data in memory
    _cached_data = {
        # Lists for easy access (same as your hardcoded format)
        "audit_names": audit_names,
        "audit_ids": audit_ids,
        "audit_categories": audit_categories,
        "device_names": device_names,
        "device_categories": device_categories,
        "audit_device_compatibility": audit_device_compatibility,
        "audit_aliases": audit_aliases,  # Keep hardcoded
        
        # Full detailed data
        "audits": audits_data,
        "devices": devices_data,
        "reports": reports_data,
        
        # Metadata
        "metadata": {
            "total_audits": len(audits_data),
            "total_devices": len(devices_data),
            "total_reports": len(reports_data),
            "last_updated": datetime.now().isoformat()
        }
    }
    
    _cache_timestamp = datetime.now()
    return _cached_data

def refresh_audits_data() -> Dict[str, Any]:
    """
    Load only audits data from database and update in memory cache
    """
    global _cached_data, _cache_timestamp
    
    logger.info("Loading audits data from database...")
    
    # Load only audits data
    audits_data = load_audits_data_from_db()
    
    # Extract lists for easy access
    audit_names = [audit["audit_name"] for audit in audits_data]
    audit_ids = [audit["audit_id"] for audit in audits_data]
    audit_categories = list(set([audit["audit_category"] for audit in audits_data]))
    
    # Generate audit device compatibility from database
    audit_device_compatibility = generate_audit_device_compatibility(audits_data)
    
    # Update cache (keep existing devices and reports data if available)
    if _cached_data is None:
        _cached_data = {}
    
    # Update audit-related data
    _cached_data.update({
        "audit_names": audit_names,
        "audit_ids": audit_ids,
        "audit_categories": audit_categories,
        "audit_device_compatibility": audit_device_compatibility,
        "audit_aliases": audit_aliases,
        "audits": audits_data,
        "metadata": {
            **(_cached_data.get("metadata", {})),
            "total_audits": len(audits_data),
            "audits_last_updated": datetime.now().isoformat()
        }
    })
    
    _cache_timestamp = datetime.now()
    
    logger.info(f"Audits data loaded successfully: {len(audits_data)} audits")
    return _cached_data

def get_cached_data() -> Optional[Dict[str, Any]]:
    """
    Get cached data from memory
    Returns None if no data is loaded yet
    """
    global _cached_data
    
    if _cached_data is None:
        logger.warning("No cached data found. Please call refresh_all_data() or refresh_audits_data() first.")
        return None
    
    return _cached_data

def get_audit_by_name(audit_name: str) -> Optional[Dict[str, Any]]:
    """Get specific audit details by name"""
    cached_data = get_cached_data()
    if not cached_data:
        return None
    
    for audit in cached_data.get("audits", []):
        if audit["audit_name"] == audit_name:
            return audit
    
    return None

def get_device_by_name(device_name: str) -> Optional[Dict[str, Any]]:
    """Get specific device details by name"""
    cached_data = get_cached_data()
    if not cached_data:
        return None
    
    for device in cached_data.get("devices", []):
        if device["device_name"] == device_name:
            return device
    
    return None

def get_compatible_devices_for_audit(audit_name: str) -> List[Dict[str, Any]]:
    """Get all devices compatible with a specific audit"""
    cached_data = get_cached_data()
    if not cached_data:
        return []
    
    audit = get_audit_by_name(audit_name)
    if not audit:
        return []
    
    compatible_categories = audit["device_categories"]
    compatible_devices = []
    
    for device in cached_data.get("devices", []):
        if device["device_category"] in compatible_categories:
            compatible_devices.append(device)
    
    return compatible_devices

# ================================================================================
# ENGINEER TASK MANAGEMENT SYSTEM - SIMPLE DATABASE OPERATIONS
# ================================================================================

def insert_engineer_task(user_id: str, request_description: str, task_type: str = "create_new_audit") -> Optional[int]:
    """
    Insert a new engineer task into the existing engineer_tasks table
    
    Args:
        user_id: Session ID of the requesting user
        request_description: Description of the audit to create
        task_type: Type of task (default: create_new_audit)
        
    Returns:
        int: Task ID if successful, None if failed
    """
    conn = get_database_connection()
    if not conn:
        logger.error("Cannot connect to database to insert engineer task")
        return None
    
    cursor = None
    try:
        cursor = conn.cursor()
        
        # Validate inputs
        if not user_id or not request_description:
            logger.error("user_id and request_description are required")
            return None
        cursor.execute("""
            INSERT INTO engineer_tasks (user_id, request_description, task_type, status)
            VALUES (%s, %s, %s, 'pending')
            RETURNING task_id;
        """, (user_id, request_description, task_type))
        
        task_id = cursor.fetchone()[0]
        conn.commit()
        logger.info(f"📝 Request saved with ID: {task_id}")        
        return task_id
        
    except psycopg2.Error as e:
        logger.error(f"❌ PostgreSQL error inserting engineer task: {e}")
        if conn:
            conn.rollback()
        return None
    except Exception as e:
        logger.error(f"❌ General error inserting engineer task: {e}")
        if conn:
            conn.rollback()
        return None
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def update_task_status(task_id: int, status: str, assigned_to: str = None, result_data: Dict = None, error_message: str = None) -> bool:
    """
    Update the status of an engineer task
    
    Args:
        task_id: ID of the task to update
        status: New status (pending, in_progress, completed, failed)
        assigned_to: Engineer ID who is working on it
        result_data: JSON data with results (audit name, file path, etc.)
        error_message: Error message if task failed
        
    Returns:
        bool: True if successful, False if failed
    """
    conn = get_database_connection()
    if not conn:
        logger.error("Cannot connect to database to update task status")
        return False
    
    cursor = None
    try:
        cursor = conn.cursor()
        
        # Validate inputs
        if not task_id or not status:
            logger.error("task_id and status are required")
            return False
        
        # Build dynamic query based on provided parameters
        update_fields = ["status = %s"]
        params = [status]
        
        if status == 'in_progress':
            update_fields.append("started_at = CURRENT_TIMESTAMP")
        elif status in ['completed', 'failed']:
            update_fields.append("completed_at = CURRENT_TIMESTAMP")
        
        if assigned_to:
            update_fields.append("assigned_to = %s")
            params.append(assigned_to)
        
        if result_data:
            update_fields.append("result_data = %s")
            params.append(json.dumps(result_data))
        
        if error_message:
            update_fields.append("error_message = %s")
            params.append(error_message)
        
        params.append(task_id)  # For WHERE clause
        
        query = f"""
            UPDATE engineer_tasks 
            SET {', '.join(update_fields)}
            WHERE task_id = %s
        """
        
        cursor.execute(query, params)
        
        if cursor.rowcount == 0:
            logger.warning(f"No task found with ID {task_id}")
            return False
        
        conn.commit()
        return True
        
    except psycopg2.Error as e:
        logger.error(f"❌ PostgreSQL error updating task status: {e}")
        if conn:
            conn.rollback()
        return False
    except Exception as e:
        logger.error(f"❌ General error updating task status: {e}")
        if conn:
            conn.rollback()
        return False
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def get_pending_tasks() -> List[Dict[str, Any]]:
    """
    Get all pending engineer tasks
    
    Returns:
        List of pending tasks
    """
    conn = get_database_connection()
    if not conn:
        logger.error("Cannot connect to database to get pending tasks")
        return []
    
    cursor = None
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT task_id, user_id, request_description, task_type, status, created_at
            FROM engineer_tasks 
            WHERE status = 'pending'
            ORDER BY created_at ASC
        """)
        
        tasks = []
        for row in cursor.fetchall():
            tasks.append({
                'task_id': row[0],
                'user_id': row[1],
                'request_description': row[2],
                'task_type': row[3],
                'status': row[4],
                'created_at': row[5]
            })
        
        logger.info(f"Retrieved {len(tasks)} pending tasks")
        return tasks
        
    except Exception as e:
        logger.error(f"Error getting pending tasks: {e}")
        return []
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()

def get_task_by_id(task_id: int) -> Optional[Dict[str, Any]]:
    """
    Get a specific task by ID
    
    Args:
        task_id: ID of the task
        
    Returns:
        Task details or None if not found
    """
    conn = get_database_connection()
    if not conn:
        logger.error("Cannot connect to database to get task by ID")
        return None
    
    cursor = None
    try:
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT task_id, user_id, request_description, task_type, status, 
                   created_at, started_at, completed_at, assigned_to, result_data, error_message
            FROM engineer_tasks 
            WHERE task_id = %s
        """, (task_id,))
        
        row = cursor.fetchone()
        if row:
            return {
                'task_id': row[0],
                'user_id': row[1],
                'request_description': row[2],
                'task_type': row[3],
                'status': row[4],
                'created_at': row[5],
                'started_at': row[6],
                'completed_at': row[7],
                'assigned_to': row[8],
                'result_data': row[9],
                'error_message': row[10]
            }
        return None
        
    except Exception as e:
        logger.error(f"❌ Error getting task by ID: {e}")
        return None
    finally:
        if cursor:
            cursor.close()
        if conn:
            conn.close()



















# """
# PostgreSQL database connection and global list data storage for the Audit Management System
# Loads all data from database into global lists and lookup dictionaries for fast access
# """

# import psycopg2
# import logging
# from datetime import datetime
# from typing import List, Dict, Any
# from config import DATABASE_CONFIG

# # Set up logging
# logging.basicConfig(level=logging.INFO)
# logger = logging.getLogger(__name__)

# # ================================================================================
# # GLOBAL DATA LISTS - Main data storage
# # ================================================================================
# global_audits_list = []
# global_devices_list = []
# global_audit_reports_list = []
# global_device_reports_list = []

# # ================================================================================
# # GLOBAL HELPER LISTS - For entity recognition
# # ================================================================================
# audit_names_list = []
# audit_categories_list = []
# device_names_list = []
# device_categories_list = []
# audit_ids_list = []
# device_ids_list = []
# audit_report_ids_list = []
# device_report_ids_list = []

# # ================================================================================
# # GLOBAL LOOKUP DICTIONARIES - For fast filtering
# # ================================================================================
# audits_by_category = {}                    # "security" → [audit_obj1, audit_obj2, ...]
# audits_by_device_category = {}             # "router" → [audit_obj1, audit_obj3, ...]
# devices_by_category = {}                   # "router" → [device_obj1, device_obj2, ...]
# audit_reports_by_audit_id = {}             # "audit_id_1" → [report_obj1, report_obj2, ...]
# device_reports_by_device_id = {}           # "device_id_1" → [report_obj1, report_obj2, ...]
# audit_reports_by_audit_category = {}       # "security" → [audit_report_obj1, ...]
# audit_reports_by_device_category = {}      # "switch" → [audit_report_obj1, ...]
# device_reports_by_device_category = {}     # "switch" → [device_report_obj1, ...]
# device_reports_by_audit_category = {}      # "security" → [device_report_obj1, ...]
# device_reports_by_audit_id = {}            # "audit_id_1" → [device_report_obj1, ...]

# def get_database_connection():
#     """Get a connection to the PostgreSQL database with proper error handling"""
#     try:
#         connection = psycopg2.connect(**DATABASE_CONFIG)
#         connection.autocommit = False
#         return connection
#     except psycopg2.OperationalError as e:
#         logger.error(f"PostgreSQL Operational Error: {e}")
#         return None
#     except psycopg2.Error as e:
#         logger.error(f"PostgreSQL Error: {e}")
#         return None
#     except Exception as e:
#         logger.error(f"General Database Error: {e}")
#         return None

# def load_all_database_data_to_global_lists():
#     """
#     Load all data from database tables into global lists and build lookup dictionaries.
    
#     Returns:
#         bool: True if all data loaded successfully, False if database connection failed
#     """
    
#     try:
#         logger.info("Loading all database data into global lists...")
        
#         # Get database connection
#         conn = get_database_connection()
#         if not conn:
#             logger.error("Database not connected. Stopping execution.")
#             return False
        
#         cursor = None
#         try:
#             cursor = conn.cursor()
            
#             # ===== STEP 1: Load Main Data Lists =====
            
#             # Load Audits
#             audit_query = """
#                 SELECT audit_id, audit_name, description, audit_category, 
#                        device_category, audit_path
#                 FROM audits 
#                 ORDER BY audit_id;
#             """
#             cursor.execute(audit_query)
#             audit_results = cursor.fetchall()
            
#             global_audits_list.clear()
#             for row in audit_results:
#                 audit = {
#                     "audit_id": str(row[0]),
#                     "audit_name": row[1],
#                     "description": row[2],
#                     "audit_category": row[3],
#                     "device_category": row[4],
#                     "audit_path": row[5]
#                 }
#                 global_audits_list.append(audit)
            
#             # Load Devices
#             device_query = """
#                 SELECT device_id, device_name, ip, username, password, 
#                        port, device_category, device_path
#                 FROM devices 
#                 ORDER BY device_id;
#             """
#             cursor.execute(device_query)
#             device_results = cursor.fetchall()
            
#             global_devices_list.clear()
#             for row in device_results:
#                 device = {
#                     "device_id": str(row[0]),
#                     "device_name": row[1],
#                     "ip": row[2],
#                     "username": row[3],
#                     "password": row[4],
#                     "port": row[5],
#                     "device_category": row[6],
#                     "device_path": row[7]
#                 }
#                 global_devices_list.append(device)
            
#             # Load Audit Reports
#             audit_reports_query = """
#                 SELECT report_id, audit_id, request_id, report_path, created_at
#                 FROM audit_reports 
#                 ORDER BY created_at DESC;
#             """
#             cursor.execute(audit_reports_query)
#             audit_reports_results = cursor.fetchall()
            
#             global_audit_reports_list.clear()
#             for row in audit_reports_results:
#                 report = {
#                     "report_id": str(row[0]),
#                     "audit_id": str(row[1]),
#                     "request_id": str(row[2]),
#                     "report_path": row[3],
#                     "created_at": row[4].isoformat() if row[4] else None
#                 }
#                 global_audit_reports_list.append(report)
            
#             # Load Device Reports
#             device_reports_query = """
#                 SELECT report_id, device_id, audit_id, report_path, created_at
#                 FROM device_reports 
#                 ORDER BY created_at DESC;
#             """
#             cursor.execute(device_reports_query)
#             device_reports_results = cursor.fetchall()
            
#             global_device_reports_list.clear()
#             for row in device_reports_results:
#                 report = {
#                     "report_id": str(row[0]),
#                     "device_id": str(row[1]),
#                     "audit_id": str(row[2]),
#                     "report_path": row[3],
#                     "created_at": row[4].isoformat() if row[4] else None
#                 }
#                 global_device_reports_list.append(report)
            
#         finally:
#             if cursor:
#                 cursor.close()
#             conn.close()
        
#         # ===== STEP 2: Build Helper Lists =====
#         logger.info("Building helper lists...")
        
#         # Clear helper lists
#         audit_names_list.clear()
#         audit_categories_list.clear()
#         device_names_list.clear()
#         device_categories_list.clear()
#         audit_ids_list.clear()
#         device_ids_list.clear()
#         audit_report_ids_list.clear()
#         device_report_ids_list.clear()
        
#         # Build audit helper lists
#         audit_categories_set = set()
#         for audit in global_audits_list:
#             audit_names_list.append(audit["audit_name"])
#             audit_ids_list.append(audit["audit_id"])
#             audit_categories_set.add(audit["audit_category"])
#         audit_categories_list.extend(sorted(list(audit_categories_set)))
        
#         # Build device helper lists
#         device_categories_set = set()
#         for device in global_devices_list:
#             device_names_list.append(device["device_name"])
#             device_ids_list.append(device["device_id"])
#             device_categories_set.add(device["device_category"])
#         device_categories_list.extend(sorted(list(device_categories_set)))
        
#         # Build report ID lists
#         for report in global_audit_reports_list:
#             audit_report_ids_list.append(report["report_id"])
        
#         for report in global_device_reports_list:
#             device_report_ids_list.append(report["report_id"])
        
#         # ===== STEP 3: Build Lookup Dictionaries =====
#         logger.info("Building lookup dictionaries...")
        
#         # Clear lookup dictionaries
#         audits_by_category.clear()
#         audits_by_device_category.clear()
#         devices_by_category.clear()
#         audit_reports_by_audit_id.clear()
#         device_reports_by_device_id.clear()
#         audit_reports_by_audit_category.clear()
#         audit_reports_by_device_category.clear()
#         device_reports_by_device_category.clear()
#         device_reports_by_audit_category.clear()
#         device_reports_by_audit_id.clear()
        
#         # Build audits_by_category
#         for audit in global_audits_list:
#             category = audit["audit_category"]
#             if category not in audits_by_category:
#                 audits_by_category[category] = []
#             audits_by_category[category].append(audit)
        
#         # Build audits_by_device_category
#         for audit in global_audits_list:
#             device_categories = audit["device_category"].split(',') if audit["device_category"] else []
#             for device_cat in device_categories:
#                 device_cat = device_cat.strip()
#                 if device_cat not in audits_by_device_category:
#                     audits_by_device_category[device_cat] = []
#                 audits_by_device_category[device_cat].append(audit)
        
#         # Build devices_by_category
#         for device in global_devices_list:
#             category = device["device_category"]
#             if category not in devices_by_category:
#                 devices_by_category[category] = []
#             devices_by_category[category].append(device)
        
#         # Build audit_reports_by_audit_id
#         for report in global_audit_reports_list:
#             audit_id = report["audit_id"]
#             if audit_id not in audit_reports_by_audit_id:
#                 audit_reports_by_audit_id[audit_id] = []
#             audit_reports_by_audit_id[audit_id].append(report)
        
#         # Build device_reports_by_device_id
#         for report in global_device_reports_list:
#             device_id = report["device_id"]
#             if device_id not in device_reports_by_device_id:
#                 device_reports_by_device_id[device_id] = []
#             device_reports_by_device_id[device_id].append(report)
        
#         # Build device_reports_by_audit_id
#         for report in global_device_reports_list:
#             audit_id = report["audit_id"]
#             if audit_id not in device_reports_by_audit_id:
#                 device_reports_by_audit_id[audit_id] = []
#             device_reports_by_audit_id[audit_id].append(report)
        
#         # Build audit_reports_by_audit_category (reports from audits of specific category)
#         for audit in global_audits_list:
#             audit_id = audit["audit_id"]
#             audit_category = audit["audit_category"]
            
#             if audit_category not in audit_reports_by_audit_category:
#                 audit_reports_by_audit_category[audit_category] = []
            
#             # Get reports for this audit
#             if audit_id in audit_reports_by_audit_id:
#                 audit_reports_by_audit_category[audit_category].extend(audit_reports_by_audit_id[audit_id])
        
#         # Build device_reports_by_audit_category (device reports from audits of specific category)
#         for audit in global_audits_list:
#             audit_id = audit["audit_id"]
#             audit_category = audit["audit_category"]
            
#             if audit_category not in device_reports_by_audit_category:
#                 device_reports_by_audit_category[audit_category] = []
            
#             # Get device reports for this audit
#             if audit_id in device_reports_by_audit_id:
#                 device_reports_by_audit_category[audit_category].extend(device_reports_by_audit_id[audit_id])
        
#         # Build audit_reports_by_device_category (audit reports from audits that ran on specific device category)
#         for audit in global_audits_list:
#             audit_id = audit["audit_id"]
#             device_categories = audit["device_category"].split(',') if audit["device_category"] else []
            
#             for device_cat in device_categories:
#                 device_cat = device_cat.strip()
#                 if device_cat not in audit_reports_by_device_category:
#                     audit_reports_by_device_category[device_cat] = []
                
#                 # Get audit reports for this audit
#                 if audit_id in audit_reports_by_audit_id:
#                     audit_reports_by_device_category[device_cat].extend(audit_reports_by_audit_id[audit_id])
        
#         # Build device_reports_by_device_category (device reports from devices of specific category)
#         for device in global_devices_list:
#             device_id = device["device_id"]
#             device_category = device["device_category"]
            
#             if device_category not in device_reports_by_device_category:
#                 device_reports_by_device_category[device_category] = []
            
#             # Get device reports for this device
#             if device_id in device_reports_by_device_id:
#                 device_reports_by_device_category[device_category].extend(device_reports_by_device_id[device_id])
        
        
#         logger.info("All database data loaded successfully into global lists and lookup dictionaries")
#         return True
        
#     except Exception as e:
#         logger.error(f"Critical error in load_all_database_data_to_global_lists(): {e}")
#         return False

# # Example usage and testing
# if __name__ == "__main__":
#     # Load all data
#     success = load_all_database_data_to_global_lists()
    
#     if success:
#         # Print summary
#         print(f"Data loaded successfully")
#     else:
#         print("Failed to load data from database")