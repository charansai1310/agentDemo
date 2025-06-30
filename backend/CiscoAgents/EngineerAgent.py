"""
WebSocket-Compatible Engineer Agent for handling MOP files and audit creation requests
Modified to work with WebSocket connections instead of console interface
"""
import os
import sys
import uuid
import re
from pathlib import Path
from datetime import datetime

# Add the parent directory to the system path to import from backend
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from autogen_core import (
    MessageContext,
    RoutedAgent,
    TopicId,
    message_handler,
)
from autogen_core.models import AssistantMessage

# Import from parent directory (backend)
from models import (
    EngineerLogin, 
    EngineerTask,
    EngineerNotification,
    CodeGenerationRequest, 
    CodeGenerationResponse, 
    CodeFeedback
)
from config import (
    ENGINEER_AGENT_TOPIC, 
    CODE_GENERATION_AGENT_TOPIC,
    ORCHESTRATOR_AGENT_TOPIC
)

# Mock database functions for when database is not available
def get_pending_tasks():
    """Mock function - returns empty list when database is not available"""
    try:
        from database import get_pending_tasks as db_get_pending_tasks
        return db_get_pending_tasks()
    except Exception as e:
        print(f"📊 Database not available: {e}")
        # Return mock data for testing
        return [
            {
                'task_id': 1,
                'user_id': 'customer_001',
                'request_description': 'Create audit for network interfaces',
                'task_type': 'audit_creation',
                'created_at': datetime.now(),
                'status': 'pending'
            },
            {
                'task_id': 2,
                'user_id': 'customer_002', 
                'request_description': 'Audit VLAN configuration on switches',
                'task_type': 'audit_creation',
                'created_at': datetime.now(),
                'status': 'pending'
            }
        ]

def update_task_status(task_id, status, assigned_to=None):
    """Mock function - does nothing when database is not available"""
    try:
        from database import update_task_status as db_update_task_status
        return db_update_task_status(task_id, status, assigned_to)
    except Exception as e:
        print(f"📊 Database not available for update: {e}")
        return True

class WebSocketEngineerAgent(RoutedAgent):
    """WebSocket-Compatible Engineer Agent for audit code generation"""
    
    def __init__(self, description: str, engineer_topic_type: str, orchestrator_topic_type: str):
        super().__init__(description)
        self._engineer_topic_type = engineer_topic_type
        self._orchestrator_topic_type = orchestrator_topic_type
        
        # Session management for WebSocket mode
        self._code_sessions = {}       # Store code generation sessions per WebSocket session
        self._session_states = {}      # Store session state per WebSocket session
        self._user_requests = {}       # Store user requests from database
        self._uploaded_files = {}      # Store uploaded file content per session

    def _extract_file_from_description(self, description: str) -> tuple[str, str, str]:
        """Extract file information from the enhanced description"""
        file_name = None
        file_content = None
        clean_description = description
        
        # Look for file markers in the description
        if "[FILE_UPLOADED:" in description:
            try:
                # Extract file name
                file_start = description.find("[FILE_UPLOADED: ") + len("[FILE_UPLOADED: ")
                file_end = description.find("]", file_start)
                if file_end > file_start:
                    file_name = description[file_start:file_end]
                
                # Extract file content (everything after the file marker)
                content_start = description.find("]\n", file_end) + 2
                if content_start > 1:
                    file_content = description[content_start:]
                
                # Clean description (everything before the file marker)
                clean_description = description[:description.find("[FILE_UPLOADED:")].strip()
                
            except Exception as e:
                print(f"🔧 Error extracting file info: {e}")
        
        # Also look for the 📁 File: format
        elif "📁 File:" in description:
            try:
                lines = description.split('\n')
                clean_lines = []
                file_lines = []
                in_file_section = False
                
                for line in lines:
                    if line.startswith("📁 File:"):
                        file_name = line.replace("📁 File:", "").strip()
                        in_file_section = True
                    elif line.startswith("📄 Content:"):
                        in_file_section = True
                    elif in_file_section:
                        file_lines.append(line)
                    else:
                        clean_lines.append(line)
                
                file_content = '\n'.join(file_lines).strip()
                clean_description = '\n'.join(clean_lines).strip()
                
            except Exception as e:
                print(f"🔧 Error extracting file info from format: {e}")
        
        return clean_description, file_name, file_content

    @message_handler
    async def handle_engineer_task(self, message: EngineerTask, ctx: MessageContext) -> None:
        """
        Handle engineer tasks from WebSocket - process single messages
        
        Args:
            message: Engineer task from WebSocket or Orchestrator
            ctx: Message context with session information
        """
        session_id = ctx.topic_id.source
        full_description = message.audit_description
        
        print(f"🔧 EngineerAgent: Processing WebSocket message from session {session_id}")
        print(f"📝 Full Description: {full_description[:100]}...")
        
        try:
            # Extract file information from description
            clean_content, file_name, file_content = self._extract_file_from_description(full_description)
            
            print(f"📝 Clean Content: {clean_content}")
            if file_name:
                print(f"📁 File detected: {file_name}")
                print(f"📄 File content length: {len(file_content) if file_content else 0}")
            
            # Initialize session state if needed
            if session_id not in self._session_states:
                self._session_states[session_id] = {
                    'current_task': None,
                    'uploaded_files': {},
                    'created_at': datetime.now()
                }
            
            # Check if this is a conversational request (not a code generation request)
            if self._is_conversational_request(clean_content):
                await self._handle_conversational_input(session_id, clean_content)
                return
            
            # Store current task info
            self._session_states[session_id]['current_task'] = {
                'task_id': message.task_id,
                'user_id': message.user_id,
                'description': clean_content,
                'task_type': message.task_type
            }
            
            # Handle file if provided
            if file_name and file_content:
                # Store file content in session
                self._session_states[session_id]['uploaded_files'][file_name] = file_content
                
                # Send confirmation that file was uploaded
                response = f"📁 File '{file_name}' processed successfully!\n"
                response += f"📄 Content preview (first 200 chars):\n"
                response += f"{file_content[:200]}{'...' if len(file_content) > 200 else ''}\n\n"
                response += f"You can now say:\n"
                response += f"• 'generate code using this file' - to generate code from the uploaded file\n"
                response += f"• 'generate code' - to generate code from the task description"
                
                await self._send_response_to_client(session_id, response)
                
            else:
                # No file provided - check if it's a direct code generation request
                if any(phrase in clean_content.lower() for phrase in ["generate code", "create code", "make code"]):
                    await self._handle_code_generation_request(session_id, clean_content)
                else:
                    # Generic response for non-code generation requests
                    response = f"🔧 EngineerAgent: I understand you want help with: {clean_content}\n\n"
                    response += f"I can help you with:\n"
                    response += f"• 'generate code for [description]' - Create audit code\n"
                    response += f"• Upload a file and say 'generate code using this file'\n"
                    response += f"• 'show pending requests' - View pending tasks\n"
                    response += f"• 'help' - Show all available commands\n\n"
                    response += f"What would you like to do?"
                    
                    await self._send_response_to_client(session_id, response)
                
        except Exception as e:
            print(f"🔧 EngineerAgent: Error processing task: {e}")
            import traceback
            traceback.print_exc()
            await self._send_error_response(session_id, f"Error processing your request: {str(e)}")

    def _is_conversational_request(self, content: str) -> bool:
        """Check if this is a conversational request rather than a code generation request"""
        content_lower = content.lower()
        
        conversational_keywords = [
            "show pending", "pending requests", "what requests",
            "status", "what's happening", "current state",
            "help", "what can you do", "commands",
            "list", "display", "view", "work on", "start task", "select task",
            "approve", "reject", "improve", "refine", "enhance", "modify", "accept", "decline"
        ]
        
        # If it contains conversational keywords, treat as conversation
        if any(keyword in content_lower for keyword in conversational_keywords):
            return True
        
        # If it's very short and doesn't mention code/generate/create, treat as conversation
        if len(content.split()) <= 3 and not any(word in content_lower for word in ["code", "generate", "create", "audit", "mop"]):
            return True
            
        return False

    async def _handle_code_generation_request(self, session_id: str, content: str):
        """Handle code generation requests"""
        content_lower = content.lower()
        
        # Check if they want to use uploaded file
        if any(phrase in content_lower for phrase in ["using this file", "use this file", "from this file", "with this file"]):
            # Look for uploaded files in this session
            uploaded_files = self._session_states.get(session_id, {}).get('uploaded_files', {})
            
            if uploaded_files:
                # Use the most recently uploaded file
                filename = list(uploaded_files.keys())[-1]
                file_content = uploaded_files[filename]
                
                response = f"🔧 EngineerAgent: I'll generate code using the file '{filename}'.\n"
                response += "Sending request to the code generator... This might take 10-30 seconds."
                
                await self._send_response_to_client(session_id, response)
                await self._send_code_generation_request(session_id, file_content, filename)
                
            else:
                response = f"🔧 EngineerAgent: I don't see any uploaded file. Please upload a file first or provide a description for direct code generation."
                await self._send_response_to_client(session_id, response)
        
        elif any(phrase in content_lower for phrase in ["generate code", "create code", "make code"]):
            # Generate code directly from task description
            current_task = self._session_states.get(session_id, {}).get('current_task')
            
            if current_task:
                audit_description = current_task['description']
                virtual_mop = self._create_virtual_mop(audit_description)
                filename = f"direct_task_{session_id}.txt"
                
                response = f"🔧 EngineerAgent: I'll generate code directly from the task description.\n"
                response += "Creating virtual MOP and sending to code generator... This might take 10-30 seconds."
                
                await self._send_response_to_client(session_id, response)
                await self._send_code_generation_request(session_id, virtual_mop, filename)
                
            else:
                # Use the content directly as the description
                virtual_mop = self._create_virtual_mop(content)
                filename = f"direct_request_{session_id}.txt"
                
                response = f"🔧 EngineerAgent: I'll generate code for: {content}\n"
                response += "Creating virtual MOP and sending to code generator... This might take 10-30 seconds."
                
                await self._send_response_to_client(session_id, response)
                await self._send_code_generation_request(session_id, virtual_mop, filename)
        
        else:
            response = f"🔧 EngineerAgent: I can help you with:\n"
            response += f"• 'generate code for [description]' - Create code from description\n"
            response += f"• 'generate code using this file' - if you've uploaded a file\n"
            response += f"What would you like to do?"
            
            await self._send_response_to_client(session_id, response)

    async def _send_code_generation_request(self, session_id: str, mop_content: str, filename: str):
        """Send request to code generation agent"""
        request = CodeGenerationRequest(
            mop_content=mop_content,
            mop_filename=filename,
            engineer_session_id=session_id,
            generation_type="initial"
        )
        
        await self.publish_message(
            request,
            topic_id=TopicId(CODE_GENERATION_AGENT_TOPIC, source=session_id)
        )
        
        print(f"📤 Request sent to code generator for session {session_id}")

    def _create_virtual_mop(self, audit_description: str) -> str:
        """Create virtual MOP content from audit description"""
        return f"""
AUDIT REQUEST: {audit_description}

OBJECTIVE:
Create an audit script based on the user's request: {audit_description}

PROCEDURE:
1. Analyze the audit requirements
2. Implement appropriate checking mechanisms  
3. Return results in structured format
4. Include proper error handling

EXPECTED OUTPUT:
- Structured audit results
- Clear success/failure indicators
- Detailed findings where applicable

IMPLEMENTATION NOTES:
- Use appropriate libraries (paramiko for SSH, netmiko for network devices)
- Include proper exception handling
- Return results in JSON or structured format
- Add logging for troubleshooting
"""

    async def _handle_conversational_input(self, session_id: str, content: str):
        """Handle conversational input without triggering code generation"""
        message = content.strip().lower()
        
        print(f"🔧 EngineerAgent: Processing conversational input: '{content}'")
        
        # Handle different conversation types
        if any(phrase in message for phrase in [
            'show pending', 'pending requests', 'what requests', 'what do we have',
            'any requests', 'tasks waiting', 'what needs doing'
        ]):
            await self._show_pending_requests(session_id)
        
        elif any(phrase in message for phrase in [
            'work on', 'start task', 'select task', "let's work on", 'tackle'
        ]):
            await self._handle_task_selection(session_id, content)

        elif any(phrase in message for phrase in [
            'approve', 'looks good', 'ship it', 'deploy', 'finalize',
            'ready to go', 'good to go', 'accept this'
        ]):
            await self._handle_code_approval(session_id, content)
        
        elif any(phrase in message for phrase in [
            'reject', 'try again', 'start over', 'not good', 'needs work',
            'cancel this', 'discard'
        ]):
            await self._handle_code_rejection(session_id, content)
        
        elif any(phrase in message for phrase in [
            'improve', 'refine', 'enhance', 'add comments', 'remove comments',
            'better error handling', 'optimize', 'clean up'
        ]):
            await self._handle_code_improvement(session_id, content)

    async def _handle_code_approval(self, session_id: str, content: str):
        """Handle code approval requests"""
        print(f"🔧 EngineerAgent: Processing code approval for session {session_id}")
        
        # Check if there's a current code session
        if session_id not in self._code_sessions:
            response = "🔧 EngineerAgent: No generated code to approve. Please generate code first."
            await self._send_response_to_client(session_id, response)
            return
        
        code_session = self._code_sessions[session_id]
        
        # Parse approval command for audit name and category
        # Expected format: approve "Audit Name" "Category"
        audit_name, category = self._parse_approval_command(content)
        
        if not audit_name or not category:
            response = f"🔧 EngineerAgent: Please provide both audit name and category.\n"
            response += f"Format: approve \"Network Interface Audit\" \"Network\"\n"
            response += f"Available categories: Network, Security, System, Configuration, Performance"
            await self._send_response_to_client(session_id, response)
            return
        
        # Send approval to Code Generation Agent
        feedback = CodeFeedback(
            session_id=session_id,
            mop_filename=code_session['mop_filename'],
            action="approve",
            audit_name=audit_name,
            category=category
        )
        
        await self.publish_message(
            feedback,
            topic_id=TopicId(CODE_GENERATION_AGENT_TOPIC, source=session_id)
        )
        
        response = f"🔧 EngineerAgent: ✅ Approving code for audit '{audit_name}' in category '{category}'...\n"
        response += f"The code will be saved and added to the audit database."
        
        await self._send_response_to_client(session_id, response)
        print(f"📤 Code approval sent to Code Generation Agent")

    async def _handle_code_rejection(self, session_id: str, content: str):
        """Handle code rejection requests"""
        print(f"🔧 EngineerAgent: Processing code rejection for session {session_id}")
        
        # Check if there's a current code session
        if session_id not in self._code_sessions:
            response = "🔧 EngineerAgent: No generated code to reject. Please generate code first."
            await self._send_response_to_client(session_id, response)
            return
        
        code_session = self._code_sessions[session_id]
        
        # Send rejection to Code Generation Agent
        feedback = CodeFeedback(
            session_id=session_id,
            mop_filename=code_session['mop_filename'],
            action="reject"
        )
        
        await self.publish_message(
            feedback,
            topic_id=TopicId(CODE_GENERATION_AGENT_TOPIC, source=session_id)
        )
        
        response = f"🔧 EngineerAgent: ❌ Code rejected.\n"
        response += f"You can:\n"
        response += f"• Generate new code with different requirements\n"
        response += f"• Upload a different MOP file\n"
        response += f"• Provide feedback for improvements"
        
        await self._send_response_to_client(session_id, response)
        print(f"📤 Code rejection sent to Code Generation Agent")

    async def _handle_code_improvement(self, session_id: str, content: str):
        """Handle code improvement/refinement requests"""
        print(f"🔧 EngineerAgent: Processing code improvement request for session {session_id}")
        
        # Check if there's a current code session
        if session_id not in self._code_sessions:
            response = "🔧 EngineerAgent: No generated code to improve. Please generate code first."
            await self._send_response_to_client(session_id, response)
            return
        
        code_session = self._code_sessions[session_id]
        
        # Extract feedback from the improvement request
        feedback_text = self._extract_improvement_feedback(content)
        
        if not feedback_text:
            response = f"🔧 EngineerAgent: Please provide specific feedback for improvement.\n"
            response += f"Examples:\n"
            response += f"• 'improve by adding error handling'\n"
            response += f"• 'refine to include more detailed logging'\n"
            response += f"• 'enhance with better variable names'\n"
            response += f"• 'modify to use different SSH library'"
            await self._send_response_to_client(session_id, response)
            return
        print({feedback_text})
        # Send improvement request to Code Generation Agent
        feedback = CodeFeedback(
            session_id=session_id,
            mop_filename=code_session['mop_filename'],
            action="refine",
            feedback=feedback_text
        )
        
        await self.publish_message(
            feedback,
            topic_id=TopicId(CODE_GENERATION_AGENT_TOPIC, source=session_id)
        )
        
        response = f"🔧 EngineerAgent: 🔄 Requesting code improvements...\n"
        response += f"Feedback: {feedback_text}\n"
        response += f"This may take 10-30 seconds to process."
        
        await self._send_response_to_client(session_id, response)
        print(f"📤 Code improvement request sent to Code Generation Agent")

    def _parse_approval_command(self, content: str) -> tuple[str, str]:
        """Parse approval command to extract audit name and category"""
        try:
            # Look for quoted strings in the content
            import re
            
            # Pattern to match approve "name" "category"
            pattern = r'approve\s+"([^"]+)"\s+"([^"]+)"'
            match = re.search(pattern, content, re.IGNORECASE)
            
            if match:
                audit_name = match.group(1).strip()
                category = match.group(2).strip()
                return audit_name, category
            
            # Alternative pattern: approve name category (without quotes)
            pattern2 = r'approve\s+(\w+(?:\s+\w+)*)\s+(\w+)$'
            match2 = re.search(pattern2, content, re.IGNORECASE)
            
            if match2:
                words = content.split()
                if len(words) >= 3:
                    # Last word is category, everything else (except "approve") is audit name
                    audit_name = ' '.join(words[1:-1])
                    category = words[-1]
                    return audit_name, category
            
            return None, None
            
        except Exception as e:
            print(f"🔧 Error parsing approval command: {e}")
            return None, None

    def _extract_improvement_feedback(self, content: str) -> str:
        """Extract feedback text from improvement request"""
        try:
            # Remove common improvement keywords and get the feedback
            content_lower = content.lower()
            
            # List of improvement keywords to remove
            keywords = [
                "improve", "refine", "enhance", "modify", "change", "fix", "better",
                "by", "to", "with", "the", "code", "it", "this"
            ]
            
            words = content.split()
            
            # Find the start of actual feedback (after improvement keywords)
            start_index = 0
            for i, word in enumerate(words):
                if word.lower() in ["improve", "refine", "enhance", "modify", "change", "fix"]:
                    start_index = i + 1
                    break
            
            # Skip common connector words
            while start_index < len(words) and words[start_index].lower() in ["by", "to", "with", "the", "code", "it", "this"]:
                start_index += 1
            
            if start_index < len(words):
                feedback = ' '.join(words[start_index:])
                return feedback.strip()
            
            # If no specific feedback found, return the whole content minus the command
            if len(words) > 1:
                return ' '.join(words[1:]).strip()
            
            return "Please provide more detailed feedback for improvement"
            
        except Exception as e:
            print(f"🔧 Error extracting improvement feedback: {e}")
            return "Please provide specific improvement requirements"

    async def _show_pending_requests(self, session_id: str):
        """Show pending user requests conversationally"""
        await self._load_pending_requests_from_db()
        
        if not self._user_requests:
            response = "🔧 EngineerAgent: There are no pending user requests at the moment."
            await self._send_response_to_client(session_id, response)
            return
        
        response = f"🔧 EngineerAgent: Here are the pending requests:\n"
        response += "─" * 50 + "\n"
        
        for request_id, request_data in self._user_requests.items():
            status_emoji = "⏳" if request_data['status'] == 'pending' else "🔧"
            response += f"{status_emoji} Request ID: {request_id}\n"
            response += f"   Description: {request_data['audit_description']}\n"
            response += f"   Received: {request_data['received_at'].strftime('%H:%M:%S')}\n\n"
        
        response += "Which request would you like to work on? Just tell me the ID number."
        
        await self._send_response_to_client(session_id, response)

    async def _handle_task_selection(self, session_id: str, user_input: str):
        """Handle task selection from conversation"""
        # Extract task ID from input
        words = user_input.split()
        task_id = None
        
        for word in words:
            if word.isdigit():
                task_id = word
                break
        
        if not task_id:
            response = f"🔧 EngineerAgent: I couldn't find a task ID in your message. Please specify which task number you'd like to work on."
            await self._send_response_to_client(session_id, response)
            return
        
        await self._load_pending_requests_from_db()
        
        if task_id not in self._user_requests:
            response = f"🔧 EngineerAgent: I couldn't find task ID '{task_id}'. Let me show you the available requests."
            await self._send_response_to_client(session_id, response)
            await self._show_pending_requests(session_id)
            return
        
        request_data = self._user_requests[task_id]
        
        # Update session state with current task
        if session_id not in self._session_states:
            self._session_states[session_id] = {
                'current_task': None,
                'uploaded_files': {},
                'created_at': datetime.now()
            }
        
        self._session_states[session_id]['current_task'] = {
            'task_id': request_data['task_id'],
            'user_id': request_data['user_id'],
            'description': request_data['audit_description'],
            'task_type': request_data.get('task_type', 'unknown')
        }
        
        # Update status in database
        try:
            update_task_status(int(task_id), 'in_progress', assigned_to='engineer_websocket')
            request_data['status'] = 'in_progress'
        except Exception as e:
            print(f"🔧 EngineerAgent: Note - couldn't update task status: {e}")
        
        response = f"🔧 EngineerAgent: Great! I'm now working on task {task_id}:\n"
        response += f"Description: {request_data['audit_description']}\n\n"
        response += f"You can either:\n"
        response += f"• Upload a file and say 'generate code using this file'\n"
        response += f"• Say 'generate code' to create code directly from the description"
        
        await self._send_response_to_client(session_id, response)

    async def _load_pending_requests_from_db(self):
        """Load pending requests from database"""
        try:
            pending_tasks = get_pending_tasks()
            
            for task in pending_tasks:
                task_id = str(task['task_id'])
                if task_id not in self._user_requests:
                    self._user_requests[task_id] = {
                        'task_id': task['task_id'],
                        'user_id': task['user_id'],
                        'request_description': task['request_description'],
                        'task_type': task['task_type'],
                        'received_at': task['created_at'],
                        'status': task['status'],
                        'audit_description': task['request_description']
                    }
        except Exception as e:
            print(f"🔧 EngineerAgent: Note - couldn't load requests from database: {e}")

    async def _show_status(self, session_id: str):
        """Show current status conversationally"""
        response = f"🔧 EngineerAgent: Here's the current status:\n"
        response += f"📊 Pending Requests: {len([r for r in self._user_requests.values() if r.get('status') == 'pending'])}\n"
        response += f"🔧 In Progress: {len([r for r in self._user_requests.values() if r.get('status') == 'in_progress'])}\n"
        response += f"💻 Code Sessions: {len(self._code_sessions)}\n"
        
        if self._session_states.get(session_id, {}).get('current_task'):
            current_task = self._session_states[session_id]['current_task']
            response += f"🎯 Current Task: {current_task['description']}\n"
        
        uploaded_files = self._session_states.get(session_id, {}).get('uploaded_files', {})
        if uploaded_files:
            response += f"📁 Uploaded Files: {', '.join(uploaded_files.keys())}\n"
        
        await self._send_response_to_client(session_id, response)

    async def _send_error_response(self, session_id: str, error_message: str):
        """Send error response to WebSocket client"""
        await self._send_response_to_client(session_id, f"❌ {error_message}")

    async def _send_response_to_client(self, session_id: str, content: str):
        """Send response back to WebSocket client"""
        try:
            # Send response directly using a simple agent response
            from autogen_core.models import AssistantMessage
            from models import AgentResponse
            
            # Create a simple response context
            context = [AssistantMessage(content=content, source="EngineerAgent")]
            
            response = AgentResponse(
                context=context,
                reply_to_topic_type=self._engineer_topic_type
            )
            
            await self.publish_message(
                response,
                topic_id=TopicId(self._engineer_topic_type, source=session_id)
            )
            
        except Exception as e:
            print(f"🔧 EngineerAgent: Error sending response: {e}")

    @message_handler
    async def handle_code_generation_response(self, message: CodeGenerationResponse, ctx: MessageContext) -> None:
        """Handle responses from Code Generation Agent"""
        session_id = message.session_id
        
        print(f"🔧 EngineerAgent: Code generation response received for session {session_id}")
        print(f"📊 Status: {message.status}")
        
        # Store session info
        self._code_sessions[session_id] = {
            'session_id': message.session_id,
            'iteration': message.iteration_number,
            'status': message.status,
            'latest_code': message.generated_code,
            'mop_filename': message.mop_filename
        }
        
        # The WebSocketResponseHandler will handle sending this to the client
        # We don't need to send it again here to avoid duplicates

    @message_handler
    async def handle_engineer_login(self, message: EngineerLogin, ctx: MessageContext) -> None:
        """
        Handle engineer login - kept for backward compatibility with console mode
        For WebSocket mode, this won't be called since we skip login messages
        """
        print("🔧 EngineerAgent: Login received (console mode)")
        print("⚠️  Note: This should not be called in WebSocket mode")

    def get_session_info(self, session_id: str) -> dict:
        """Get information about a WebSocket session"""
        return {
            'session_state': self._session_states.get(session_id, {}),
            'code_sessions': self._code_sessions.get(session_id, {}),
            'active': session_id in self._session_states
        }

def create_websocket_engineer_agent(orchestrator_topic_type: str = None):
    """Factory function to create a WebSocket-compatible Engineer Agent"""
    return WebSocketEngineerAgent(
        description="WebSocket-compatible engineer agent for audit code generation.",
        engineer_topic_type=ENGINEER_AGENT_TOPIC,
        orchestrator_topic_type=orchestrator_topic_type or ORCHESTRATOR_AGENT_TOPIC
    )

def create_engineer_agent(orchestrator_topic_type: str = None):
    """
    Factory function for compatibility with existing code
    Returns the WebSocket-compatible version
    """
    return create_websocket_engineer_agent(orchestrator_topic_type)