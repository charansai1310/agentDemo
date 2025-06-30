"""
Audit Retrieval Agent for handling various audit data retrieval operations
Updated to use direct database queries for retrieval operations
"""

import json
from typing import List, Dict, Any, Optional
import os, sys
from datetime import datetime

from autogen_core import (
    MessageContext,
    RoutedAgent,
    TopicId,
    message_handler,
)
from autogen_core.models import (
    AssistantMessage,
    UserMessage,
    SystemMessage,
)

current_dir = os.path.dirname(os.path.abspath(__file__))  # CiscoAgents/
parent_dir = os.path.dirname(current_dir)                 # backend/
sys.path.insert(0, parent_dir)

from models import UserTask, AgentResponse
from entity_extractor import create_entity_extractor
from database import get_database_connection
from config import (
    ORCHESTRATOR_AGENT_TOPIC,
    AUDIT_RETRIEVAL_AGENT_TOPIC, 
)

class AuditRetrievalAgent(RoutedAgent):
    """Audit Retrieval Agent that handles different data retrieval operations using direct database queries"""
    
    def __init__(
        self,
        description: str,
        agent_topic_type: str,
        orchestrator_topic_type: str,
    ) -> None:
        super().__init__(description)
        self._agent_topic_type = agent_topic_type
        self._orchestrator_topic_type = orchestrator_topic_type
        
        # Initialize entity extractor (still uses cached data)
        self.entity_extractor = create_entity_extractor()
    
    def get_audits_from_db(self, entities: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Retrieve audits from database with filtering based on entities"""
        conn = get_database_connection()
        if not conn:
            return []
        
        cursor = None
        try:
            cursor = conn.cursor()
            
            # Base query
            query = """
                SELECT audit_id, audit_name, category, tags, description, device_categories
                FROM audits 
                WHERE 1=1
            """
            params = []
            
            # Add filters based on entities
            if "audit_id" in entities:
                query += " AND audit_id = %s"
                params.append(entities["audit_id"]["value"])
            elif "audit_name" in entities:
                query += " AND audit_name = %s"
                params.append(entities["audit_name"]["value"])
            elif "audit_category" in entities:
                query += " AND category = %s"
                params.append(entities["audit_category"]["value"])
            
            # Filter by device compatibility if device is specified
            if "device_category" in entities:
                query += " AND device_categories LIKE %s"
                params.append(f"%{entities['device_category']['value']}%")
            
            query += " ORDER BY audit_id"
            
            cursor.execute(query, params)
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
            print(f"Error retrieving audits from database: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            conn.close()
    
    def get_devices_from_db(self, entities: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Retrieve devices from database with filtering based on entities"""
        conn = get_database_connection()
        if not conn:
            return []
        
        cursor = None
        try:
            cursor = conn.cursor()
            
            # Base query
            query = """
                SELECT device_id, device_name, category
                FROM devices 
                WHERE 1=1
            """
            params = []
            
            # Add filters based on entities
            if "device_name" in entities:
                query += " AND device_name = %s"
                params.append(entities["device_name"]["value"])
            elif "device_category" in entities:
                query += " AND category = %s"
                params.append(entities["device_category"]["value"])
            
            query += " ORDER BY device_id"
            
            cursor.execute(query, params)
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
            print(f"Error retrieving devices from database: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            conn.close()
    
    def get_reports_from_db(self, entities: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Retrieve reports from database with filtering based on entities"""
        conn = get_database_connection()
        if not conn:
            return []
        
        cursor = None
        try:
            cursor = conn.cursor()
            
            # Base query
            query = """
                SELECT report_id, audit_id, device_id, audit_name, device_name, 
                       execution_time, status, results
                FROM reports 
                WHERE 1=1
            """
            params = []
            
            # Add filters based on entities
            if "audit_id" in entities:
                query += " AND audit_id = %s"
                params.append(entities["audit_id"]["value"])
            elif "audit_name" in entities:
                query += " AND audit_name = %s"
                params.append(entities["audit_name"]["value"])
            elif "audit_category" in entities:
                # Need to filter by audits in this category
                query += """ AND audit_id IN (
                    SELECT audit_id FROM audits WHERE category = %s
                )"""
                params.append(entities["audit_category"]["value"])
            
            if "device_name" in entities:
                query += " AND device_name = %s"
                params.append(entities["device_name"]["value"])
            elif "device_category" in entities:
                # Need to filter by devices in this category
                query += """ AND device_id IN (
                    SELECT device_id FROM devices WHERE category = %s
                )"""
                params.append(entities["device_category"]["value"])
            
            # Add time filtering if specified
            if "time_range" in entities:
                start_date, end_date = self.parse_time_range(entities["time_range"])
                if start_date and end_date:
                    query += " AND execution_time BETWEEN %s AND %s"
                    params.extend([start_date, end_date])
            
            query += " ORDER BY execution_time DESC"
            
            cursor.execute(query, params)
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
            print(f"Error retrieving reports from database: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            conn.close()
    
    def parse_time_range(self, time_entity: Dict[str, Any]) -> tuple:
        """Parse time entity into start and end datetime objects (same as entity_extractor)"""
        if not time_entity:
            return None, None
        
        from datetime import timedelta
        now = datetime.now()
        
        if time_entity.get("type") == "relative":
            days_offset = time_entity.get("days_offset", 0)
            time_type = time_entity.get("time_type", "")
            
            if time_type == "week":
                # For week, get start of week
                start_date = now + timedelta(days=days_offset)
                start_date = start_date - timedelta(days=start_date.weekday())  # Monday
                start_date = start_date.replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = start_date + timedelta(days=6, hours=23, minutes=59, seconds=59)  # End of Sunday
            elif time_type == "month":
                if days_offset == 0:  # This month
                    start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                    next_month = start_date.replace(month=start_date.month + 1) if start_date.month < 12 else start_date.replace(year=start_date.year + 1, month=1)
                    end_date = next_month - timedelta(seconds=1)  # End of this month
                else:  # Last month
                    start_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                    start_date = start_date.replace(month=start_date.month - 1) if start_date.month > 1 else start_date.replace(year=start_date.year - 1, month=12)
                    end_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0) - timedelta(seconds=1)
            elif time_type == "day":
                if days_offset == 0:  # Today
                    start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
                    end_date = now.replace(hour=23, minute=59, second=59, microsecond=999999)
                elif days_offset == -1:  # Yesterday
                    yesterday = now - timedelta(days=1)
                    start_date = yesterday.replace(hour=0, minute=0, second=0, microsecond=0)
                    end_date = yesterday.replace(hour=23, minute=59, second=59, microsecond=999999)
                else:  # Other days
                    target_date = now + timedelta(days=days_offset)
                    start_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
                    end_date = target_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            else:
                # For general relative time (like "last N days")
                if days_offset < 0:
                    # Past days - from N days ago to now
                    start_date = (now + timedelta(days=days_offset)).replace(hour=0, minute=0, second=0, microsecond=0)
                    end_date = now
                else:
                    # Future days (shouldn't happen much, but handle it)
                    start_date = now
                    end_date = (now + timedelta(days=days_offset)).replace(hour=23, minute=59, second=59, microsecond=999999)
            
            return start_date, end_date
        
        elif time_entity.get("type") == "absolute":
            year = time_entity.get("year")
            month = time_entity.get("month")
            
            if year and month:
                from datetime import timedelta
                start_date = datetime(year, month, 1, 0, 0, 0, 0)
                if month == 12:
                    end_date = datetime(year + 1, 1, 1, 0, 0, 0, 0) - timedelta(seconds=1)
                else:
                    end_date = datetime(year, month + 1, 1, 0, 0, 0, 0) - timedelta(seconds=1)
                return start_date, end_date
        
        return None, None
    
    def format_audit_data(self, audits: List[Dict[str, Any]]) -> str:
        """Format audit data for user display"""
        if not audits:
            return "No audits found."
        
        formatted = "Available Audits:\n\n"
        for audit in audits:
            formatted += f"{audit['audit_id']}. {audit['audit_name']}\n"
            formatted += f"Category: {audit['audit_category']}\n"
            formatted += f"Description: {audit['description']}\n"
            if audit.get('device_categories'):
                formatted += f"Compatible Devices: {', '.join(audit['device_categories'])}\n"
            formatted += "\n"
        
        return formatted
    
    def format_device_data(self, devices: List[Dict[str, Any]]) -> str:
        """Format device data for user display"""
        if not devices:
            return "No devices found."
        
        formatted = "Available Devices:\n\n"
        for device in devices:
            formatted += f"{device['device_id']}. {device['device_name']}\n"
            formatted += f"   Category: {device['device_category']}\n\n"
        
        return formatted
    
    def format_report_data(self, reports: List[Dict[str, Any]]) -> str:
        """Format report data for user display"""
        if not reports:
            return "No reports found."
        
        formatted = "**Audit Reports:**\n\n"
        for i, report in enumerate(reports[:10]):  # Limit to 10 most recent
            formatted += f"Report {report['report_id']}\n"
            formatted += f"   Audit: {report['audit_name']}\n"
            formatted += f"   Device: {report['device_name']}\n"
            formatted += f"   Status: {report['status']}\n"
            formatted += f"   Executed: {report['execution_time']}\n"
            if report.get('results'):
                # Truncate long results
                results = report['results'][:200] + "..." if len(report['results']) > 200 else report['results']
                formatted += f"   Results: {results}\n"
            formatted += "\n"
        
        if len(reports) > 10:
            formatted += f"... and {len(reports) - 10} more reports.\n"
        
        return formatted
    
    def create_formatted_response(self, entities: Dict[str, Any], retrieval_type: str) -> str:
        """
        Create formatted user-friendly response using direct database queries
        
        Args:
            entities: Extracted entities from entity extractor
            retrieval_type: Type of data to retrieve (audits, devices, reports)
            
        Returns:
            str: Formatted response for user
        """
        try:
            # Get data from database based on retrieval type
            if retrieval_type == "reports":
                data = self.get_reports_from_db(entities)
                formatted_data = self.format_report_data(data)
                count = len(data)
                message = f"Found {count} reports matching your criteria." if count > 0 else "No reports found matching your criteria."
            elif retrieval_type == "devices":
                data = self.get_devices_from_db(entities)
                formatted_data = self.format_device_data(data)
                count = len(data)
                message = f"Found {count} devices matching your criteria." if count > 0 else "No devices found matching your criteria."
            else:  # audits
                data = self.get_audits_from_db(entities)
                formatted_data = self.format_audit_data(data)
                count = len(data)
                message = f"Found {count} audits matching your criteria." if count > 0 else "No audits found matching your criteria."
            
            # Combine message and formatted data
            response = f"{message}\n\n{formatted_data}"
            
            return response
            
        except Exception as e:
            return f"❌ Error retrieving data from database: {str(e)}"
    
    @message_handler
    async def handle_task(self, message: UserTask, ctx: MessageContext) -> None:
        """
        Handle incoming tasks - uses entity extractor for parsing and database for retrieval
        
        Args:
            message: User task from orchestrator with intent and action
            ctx: Message context
        """
        # Extract intent, action, and user message for logging
        intent = getattr(message, "intent", "UNKNOWN")
        action = getattr(message, "action", "unknown")
        original_message = getattr(message, "original_message", "")
        
        print(f"AuditRetrievalAgent: Received task - Intent: {intent}, Action: {action}")
        print(f"AuditRetrievalAgent: Processing query: '{original_message}'")
        
        try:
            # Use EntityExtractor to extract entities (still uses cached data for this)
            extractor_response = self.entity_extractor.get_filtered_data(original_message)
            
            # Extract entities and retrieval type
            entities = extractor_response.get("entities_found", {})
            retrieval_type = entities.get("retrieval_type", {}).get("value", "audits")
            
            print(f"AuditRetrievalAgent: Extracted entities: {entities}")
            print(f"AuditRetrievalAgent: Retrieval type: {retrieval_type}")
            
            # Get formatted response using direct database queries
            formatted_response = self.create_formatted_response(entities, retrieval_type)
            
            # Get summary info from database
            if retrieval_type == "reports":
                db_data = self.get_reports_from_db(entities)
            elif retrieval_type == "devices":
                db_data = self.get_devices_from_db(entities)
            else:
                db_data = self.get_audits_from_db(entities)
            
            # Extract results for the AgentResponse
            results = {
                "retrieval_type": retrieval_type,
                "summary": {
                    f"total_{retrieval_type}": len(db_data)
                },
                "entities_found": entities,
                "data": {retrieval_type: db_data}
            }
            
            print(f"AuditRetrievalAgent: Successfully processed - Retrieved {len(db_data)} {retrieval_type}")
            
            # Add response to context
            message.context.append(
                AssistantMessage(content=formatted_response, source=self.id.type)
            )
            
            # Send response back to orchestrator
            await self.publish_message(
                AgentResponse(
                    context=message.context, 
                    reply_to_topic_type=self._agent_topic_type,
                    results=results
                ),
                topic_id=TopicId(self._orchestrator_topic_type, source=self.id.key),
            )
            
        except Exception as e:
            print(f"AuditRetrievalAgent: Error processing request: {e}")
            error_response = f"❌ Sorry, I encountered an error while processing your request: {str(e)}"
            
            # Add error response to context
            message.context.append(
                AssistantMessage(content=error_response, source=self.id.type)
            )
            
            # Send error response back to orchestrator
            await self.publish_message(
                AgentResponse(
                    context=message.context, 
                    reply_to_topic_type=self._agent_topic_type,
                    results={"error": str(e)}
                ),
                topic_id=TopicId(self._orchestrator_topic_type, source=self.id.key),
            )


def create_audit_retrieval_agent() -> AuditRetrievalAgent:
    """Factory function to create an Audit Retrieval Agent"""
    
    return AuditRetrievalAgent(
        description="An audit retrieval agent that handles various data retrieval operations using direct database queries.",
        agent_topic_type=AUDIT_RETRIEVAL_AGENT_TOPIC,
        orchestrator_topic_type=ORCHESTRATOR_AGENT_TOPIC,
    )


# Example usage for testing
if __name__ == "__main__":
    import asyncio
    from autogen_core.models import UserMessage
    
    async def test_agent():
        # Create agent
        agent = create_audit_retrieval_agent()
        
        # Test different queries
        test_cases = [
            "show me all audits",
            "list security audits", 
            "show me audit history",
            "get devices information",
            "show reports from last week"
        ]
        
        for test_query in test_cases:
            print(f"\n{'='*60}")
            print(f"Testing query: {test_query}")
            print(f"{'='*60}")
            
            # Test the entity extractor and database retrieval
            extractor_response = agent.entity_extractor.get_filtered_data(test_query)
            entities = extractor_response.get("entities_found", {})
            retrieval_type = entities.get("retrieval_type", {}).get("value", "audits")
            
            formatted_response = agent.create_formatted_response(entities, retrieval_type)
            
            print(f"Entities: {entities}")
            print(f"Retrieval Type: {retrieval_type}")
            print(f"Response Preview: {formatted_response[:200]}...")
    
    # Run tests
    asyncio.run(test_agent())