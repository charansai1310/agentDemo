"""
WebSocket API Server for Audit Management System
Bridges React frontend with existing agent system
"""
import asyncio
import json
import logging
import uuid
import websockets
import sys
import os
from datetime import datetime
from typing import Dict, Set, Optional
from pathlib import Path

# Add current directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from autogen_core import SingleThreadedAgentRuntime, TopicId, TypeSubscription, RoutedAgent, MessageContext, message_handler
from autogen_core.models import UserMessage
from autogen_ext.models.openai import OpenAIChatCompletionClient

# Import your existing config and models
from config import (
    USER_TOPIC,
    ENGINEER_AGENT_TOPIC,
    ORCHESTRATOR_AGENT_TOPIC,
    AUDIT_RETRIEVAL_AGENT_TOPIC,
    EXECUTE_AUDIT_AGENT_TOPIC,
    CODE_GENERATION_AGENT_TOPIC,
    OPENAI_API_KEY,
    OPENAI_MODEL
)
from models import UserTask, EngineerTask, AgentResponse, CodeGenerationResponse, EngineerNotification

# Import your agent factories
from CiscoAgents.UserAgent import create_user_agent
from CiscoAgents.OrchestratorAgent import create_orchestrator_agent
from CiscoAgents.AuditRetrievalAgent import create_audit_retrieval_agent
from CiscoAgents.AuditExecutionAgent import create_audit_execution_agent
from CiscoAgents.EngineerAgent import create_engineer_agent
from CiscoAgents.CodeGenerationAgent import create_code_generation_agent

class WebSocketResponseHandler(RoutedAgent):
    """Special agent to handle responses and route them back to WebSocket clients"""
    
    def __init__(self, websocket_server):
        super().__init__("WebSocket Response Handler")
        self.websocket_server = websocket_server
        self.processed_messages = {}  # session_id -> set of processed message hashes
    
    def _get_message_hash(self, session_id: str, content: str) -> str:
        """Create a unique hash for a message"""
        import hashlib
        # Create hash based on session + content + timestamp (rounded to nearest second)
        timestamp = int(datetime.now().timestamp())
        unique_str = f"{session_id}:{content[:100]}:{timestamp}"
        return hashlib.md5(unique_str.encode()).hexdigest()[:12]
    
    def _is_duplicate(self, session_id: str, content: str) -> bool:
        """Check if this message was already processed for this session"""
        if session_id not in self.processed_messages:
            self.processed_messages[session_id] = set()
        
        msg_hash = self._get_message_hash(session_id, content)
        
        if msg_hash in self.processed_messages[session_id]:
            return True
        
        # Add to processed and clean up if too many
        self.processed_messages[session_id].add(msg_hash)
        
        # Keep only last 20 messages per session
        if len(self.processed_messages[session_id]) > 20:
            old_messages = list(self.processed_messages[session_id])[:10]
            for old_msg in old_messages:
                self.processed_messages[session_id].discard(old_msg)
        
        return False
    
    def _is_audit_retrieval_response(self, content: str) -> bool:
        """Check if this is a legitimate audit retrieval response"""
        audit_indicators = [
            "found", "reports", "audits", "devices",
            "audit reports:", "available audits:", "available devices:",
            "no reports found", "no audits found", "no devices found",
            "matching your criteria", "report ", "audit ", "device "
        ]
        return any(indicator in content.lower() for indicator in audit_indicators)
    
    def _should_filter_for_customer(self, content: str, user_type: str) -> bool:
        """Determine if content should be filtered for customer users"""
        if user_type != "Customer":
            return False
        
        # ALLOW audit retrieval responses for customers
        if self._is_audit_retrieval_response(content):
            return False
        
        # FILTER technical engineering responses for customers
        technical_phrases = [
            "code generation complete", 
            "```python", 
            "generating code", 
            "mop file",
            "validation failed",
            "paramiko",
            "session_id",
            "iteration"
        ]
        
        if any(phrase in content.lower() for phrase in technical_phrases):
            return True
        
        # ALLOW customer-friendly messages
        customer_friendly = [
            "forwarded to our engineering team",
            "engineer to process",
            "audit creation request",
            "please wait for the engineer",
            "successfully created",
            "completed successfully"
        ]
        
        if any(phrase in content.lower() for phrase in customer_friendly):
            return False
        
        # FILTER other technical keywords
        technical_keywords = ["approve", "reject", "details:", "status:"]
        if any(keyword in content.lower() for keyword in technical_keywords):
            # But don't filter if it's clearly an audit result
            if not self._is_audit_retrieval_response(content):
                return True
        
        return False
    
    @message_handler
    async def handle_agent_response(self, message: AgentResponse, ctx: MessageContext) -> None:
        """Handle responses from any agent and route to correct WebSocket client"""
        try:
            session_id = ctx.topic_id.source
            
            # Only handle responses for connected WebSocket clients
            if session_id not in self.websocket_server.connected_clients:
                self.websocket_server.logger.debug(f"No connected client for session {session_id}")
                return
            
            client_info = self.websocket_server.connected_clients[session_id]
            user_type = client_info["user_type"]
            
            # Extract response content
            response_content = ""
            if message.context and len(message.context) > 0:
                last_message = message.context[-1]
                if hasattr(last_message, 'content'):
                    response_content = last_message.content
            
            if not response_content:
                response_content = "Request processed successfully."
            
            # Check if we should filter this response
            if self._should_filter_for_customer(response_content, user_type):
                self.websocket_server.logger.info(f"Filtering technical response from {user_type} view: {session_id}")
                return
            
            # Check for duplicates BEFORE sending
            if self._is_duplicate(session_id, response_content):
                self.websocket_server.logger.info(f"Skipping duplicate response for {session_id}")
                return
            
            # Log the response being sent
            self.websocket_server.logger.info(f"Sending AgentResponse to {user_type} {session_id}: {response_content[:50]}...")
            
            # Send response to the correct WebSocket client
            await self.websocket_server.send_response_to_client(session_id, response_content)
            
        except Exception as e:
            self.websocket_server.logger.error(f"Error handling agent response: {e}")
            import traceback
            traceback.print_exc()
    
    @message_handler 
    async def handle_code_generation_response(self, message: CodeGenerationResponse, ctx: MessageContext) -> None:
        """Handle responses from Code Generation Agent - ONLY for Engineers"""
        try:
            session_id = ctx.topic_id.source
            
            # Only handle responses for connected WebSocket clients
            if session_id not in self.websocket_server.connected_clients:
                return
            
            client_info = self.websocket_server.connected_clients[session_id]
            user_type = client_info["user_type"]
            
            # ONLY send code generation responses to Engineers, NOT Customers
            if user_type != "Engineer":
                self.websocket_server.logger.info(f"Filtering CodeGenerationResponse from {user_type} view: {session_id}")
                return
            
            # Format code generation response
            response_content = f"🤖 Code Generation Complete!\n"
            response_content += f"Status: {message.status}\n"
            if message.explanation:
                response_content += f"Details: {message.explanation}\n\n"
            
            response_content += f"📄 Generated Code:\n"
            response_content += f"```python\n{message.generated_code}\n```\n"
            
            if message.status == "generated":
                response_content += f"\nYou can now approve this code or provide feedback for improvements."
            
            # Check for duplicates BEFORE sending
            if self._is_duplicate(session_id, response_content):
                self.websocket_server.logger.info(f"Skipping duplicate code response for {session_id}")
                return
            
            self.websocket_server.logger.info(f"Sending CodeGenerationResponse to Engineer {session_id}")
            await self.websocket_server.send_response_to_client(session_id, response_content)
            
        except Exception as e:
            self.websocket_server.logger.error(f"Error handling code generation response: {e}")
    
    @message_handler
    async def handle_engineer_notification(self, message: EngineerNotification, ctx: MessageContext) -> None:
        """Handle notifications from Engineer Agent"""
        try:
            session_id = ctx.topic_id.source
            
            # Only handle notifications for connected WebSocket clients
            if session_id not in self.websocket_server.connected_clients:
                return
            
            client_info = self.websocket_server.connected_clients[session_id]
            user_type = client_info["user_type"]
            
            # Skip system messages (like "response") - only show meaningful notifications
            if message.message == "response":
                # For engineer responses, only show to engineers
                if user_type == "Engineer":
                    response_content = message.details if hasattr(message, 'details') and message.details else ""
                    if not response_content:
                        return  # Skip empty responses
                else:
                    return  # Don't show engineer technical responses to customers
            else:
                # Format notification - these can go to customers (completion notifications)
                if message.message == "completed":
                    response_content = f"✅ Audit '{message.audit_name}' has been completed successfully!"
                elif message.message == "created":
                    response_content = f"🎉 Audit '{message.audit_name}' has been created!"
                else:
                    response_content = f"📢 Update: Audit '{message.audit_name}' {message.message}"
                
                if hasattr(message, 'details') and message.details:
                    response_content += f"\nDetails: {message.details}"
            
            # Check for duplicates BEFORE sending
            if self._is_duplicate(session_id, response_content):
                self.websocket_server.logger.info(f"Skipping duplicate notification for {session_id}")
                return
            
            self.websocket_server.logger.info(f"Sending EngineerNotification to {user_type} {session_id}")
            await self.websocket_server.send_response_to_client(session_id, response_content)
            
        except Exception as e:
            self.websocket_server.logger.error(f"Error handling engineer notification: {e}")

class WebSocketServer:
    """WebSocket server that bridges frontend to agent system"""
    
    def __init__(self, host="localhost", port=8080):
        self.host = host
        self.port = port
        self.runtime: Optional[SingleThreadedAgentRuntime] = None
        self.model_client: Optional[OpenAIChatCompletionClient] = None
        self.connected_clients: Dict[str, dict] = {}  # session_id -> {websocket, user_type}
        self.pending_responses: Dict[str, str] = {}  # topic_source -> session_id mapping
        self.logger = self._setup_logging()
        self.session_files: Dict[str, dict] = {}  # Store file data per session
        
    def _setup_logging(self):
        """Setup logging for WebSocket server"""
        logging.basicConfig(level=logging.INFO)
        logging.getLogger('autogen_core').setLevel(logging.WARNING)
        logging.getLogger('autogen_core.events').setLevel(logging.WARNING)
        logging.getLogger('httpx').setLevel(logging.WARNING)
        return logging.getLogger('WebSocketServer')
    
    async def initialize_agent_system(self):
        """Initialize agent runtime and register all agents"""
        try:
            # Initialize runtime and model client
            self.runtime = SingleThreadedAgentRuntime()
            self.model_client = OpenAIChatCompletionClient(
                model=OPENAI_MODEL,
                api_key=OPENAI_API_KEY,
            )
            
            # Register WebSocket response handler first
            await self.register_response_handler()
            
            # Register all agents (same as main.py)
            agents_config = [
                {
                    'name': 'User Agent',
                    'topic': USER_TOPIC,
                    'factory': lambda: create_user_agent()
                },
                {
                    'name': 'Orchestrator Agent',
                    'topic': ORCHESTRATOR_AGENT_TOPIC,
                    'factory': lambda: create_orchestrator_agent(self.model_client)
                },
                {
                    'name': 'Audit Retrieval Agent',
                    'topic': AUDIT_RETRIEVAL_AGENT_TOPIC,
                    'factory': lambda: create_audit_retrieval_agent()
                },
                {
                    'name': 'Audit Execution Agent',
                    'topic': EXECUTE_AUDIT_AGENT_TOPIC,
                    'factory': lambda: create_audit_execution_agent()
                },
                {
                    'name': 'Engineer Agent',
                    'topic': ENGINEER_AGENT_TOPIC,
                    'factory': lambda: create_engineer_agent(ORCHESTRATOR_AGENT_TOPIC)
                },
                {
                    'name': 'Code Generation Agent',
                    'topic': CODE_GENERATION_AGENT_TOPIC,
                    'factory': lambda: create_code_generation_agent()
                }
            ]
            
            # Register each agent
            for agent_config in agents_config:
                agent_type = await agent_config['factory']().register(
                    self.runtime,
                    type=agent_config['topic'],
                    factory=agent_config['factory'],
                )
                
                await self.runtime.add_subscription(
                    TypeSubscription(topic_type=agent_config['topic'], agent_type=agent_type.type)
                )
                
                self.logger.info(f"Registered {agent_config['name']}")
            
            # Start the runtime
            self.runtime.start()
            self.logger.info("Agent system initialized successfully")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to initialize agent system: {e}")
            return False
    
    async def handle_client_connection(self, websocket):
        """Handle new WebSocket client connection"""
        # Extract path from websocket if needed
        path = getattr(websocket, 'path', '/')
        
        session_id = str(uuid.uuid4())[:8]
        self.logger.info(f"New client connected: {session_id}")
        
        try:
            # Wait for authentication message
            auth_message = await websocket.recv()
            auth_data = json.loads(auth_message)
            
            if auth_data.get("type") != "auth":
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": "First message must be authentication"
                }))
                return
            
            # Validate credentials
            username = auth_data.get("username")
            password = auth_data.get("password")
            
            user_type = self.authenticate_user(username, password)
            if not user_type:
                await websocket.send(json.dumps({
                    "type": "error", 
                    "message": "Invalid credentials"
                }))
                return
            
            # Store client info
            self.connected_clients[session_id] = {
                "websocket": websocket,
                "user_type": user_type,
                "username": username
            }
            
            # Initialize session file storage
            self.session_files[session_id] = {}
            
            # Send authentication success
            await websocket.send(json.dumps({
                "type": "auth_success",
                "user_type": user_type,
                "session_id": session_id
            }))
            
            self.logger.info(f"Client {session_id} authenticated as {user_type}")
            
            # Handle messages
            async for message in websocket:
                await self.handle_client_message(session_id, message)
                
        except websockets.exceptions.ConnectionClosed:
            self.logger.info(f"Client {session_id} disconnected")
        except Exception as e:
            self.logger.error(f"Error handling client {session_id}: {e}")
        finally:
            if session_id in self.connected_clients:
                del self.connected_clients[session_id]
            if session_id in self.session_files:
                del self.session_files[session_id]
    
    def authenticate_user(self, username: str, password: str) -> Optional[str]:
        """Authenticate user and return user type"""
        if username == "Customer" and password == "Customer@123":
            return "Customer"
        elif username == "Engineer" and password == "Engineer@123":
            return "Engineer"
        else:
            return None
    
    def _process_uploaded_file(self, file_data: dict) -> tuple[str, str]:
        """Process uploaded file and return (filename, content)"""
        try:
            file_name = file_data.get("name", "unknown_file")
            file_content = file_data.get("content", "")
            
            # Handle different file types
            if file_name.lower().endswith(('.docx', '.doc')):
                if file_content.startswith('data:'):
                    try:
                        import base64
                        import io
                        # Extract base64 part
                        base64_data = file_content.split(',')[1]
                        binary_data = base64.b64decode(base64_data)
                        
                        # Try to extract text using python-docx
                        try:
                            import docx
                            doc = docx.Document(io.BytesIO(binary_data))
                            extracted_text = ""
                            for paragraph in doc.paragraphs:
                                extracted_text += paragraph.text + "\n"
                            
                            if extracted_text.strip():
                                file_content = extracted_text.strip()
                            else:
                                file_content = "DOCX file uploaded but appears to be empty."
                                
                        except ImportError:
                            file_content = "DOCX file uploaded. Note: python-docx not available for full text extraction."
                        except Exception as e:
                            file_content = f"DOCX file uploaded but could not be processed: {str(e)}"
                            
                    except Exception as e:
                        file_content = f"Error processing DOCX file: {str(e)}"
                        
            elif file_name.lower().endswith('.txt'):
                # For text files, content should already be text
                if file_content.startswith('data:'):
                    try:
                        import base64
                        base64_data = file_content.split(',')[1]
                        file_content = base64.b64decode(base64_data).decode('utf-8')
                    except Exception as e:
                        file_content = f"Error processing text file: {str(e)}"
            
            return file_name, file_content
            
        except Exception as e:
            return "error_file", f"Error processing uploaded file: {str(e)}"
    
    async def handle_client_message(self, session_id: str, message: str):
        """Handle message from WebSocket client"""
        try:
            data = json.loads(message)
            client_info = self.connected_clients.get(session_id)
            
            if not client_info:
                return
            
            user_type = client_info["user_type"]
            websocket = client_info["websocket"]
            
            # Extract message content and optional file
            content = data.get("content", "")
            file_data = data.get("file")
            
            if not content:
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": "Message content is required"
                }))
                return
            
            # Process file upload if provided
            file_info = None
            if file_data:
                file_name, file_content = self._process_uploaded_file(file_data)
                self.session_files[session_id][file_name] = file_content
                file_info = {"name": file_name, "content": file_content}
                self.logger.info(f"File uploaded for session {session_id}: {file_name}")
            
            # Create enhanced content with file information
            enhanced_content = content
            if file_info:
                enhanced_content = f"{content}\n\n[FILE_UPLOADED: {file_info['name']}]\n{file_info['content'][:500]}{'...' if len(file_info['content']) > 500 else ''}"
            
            # Create message context
            user_message = UserMessage(content=enhanced_content, source="User")
            context = [user_message]
            
            # Route based on user type
            if user_type == "Customer":
                # Route to UserAgent
                task = UserTask(
                        context=context,
                        original_message=content,
                        client_session_id=session_id  
                    )
                topic = USER_TOPIC
                
            elif user_type == "Engineer":
                # Create standard EngineerTask - but enhance the description to include file info
                task_description = content
                if file_info:
                    task_description = f"{content}\n\n📁 File: {file_info['name']}\n📄 Content:\n{file_info['content']}"
                
                task = EngineerTask(
                    task_id=0,  # Placeholder
                    user_id=session_id,
                    audit_description=task_description,
                    task_type="chat_request"
                )
                topic = ENGINEER_AGENT_TOPIC
                
            else:
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": "Invalid user type"
                }))
                return
            
            # Send to agent system
            await self.runtime.publish_message(
                task,
                topic_id=TopicId(topic, source=session_id)
            )
            
            # Store the mapping for response handling
            self.pending_responses[session_id] = session_id
            
        except json.JSONDecodeError:
            await self.send_error(session_id, "Invalid JSON message")
        except Exception as e:
            self.logger.error(f"Error processing message from {session_id}: {e}")
            import traceback
            traceback.print_exc()
            await self.send_error(session_id, f"Error processing message: {str(e)}")
    
    async def register_response_handler(self):
        """Register the WebSocket response handler agent"""
        try:
            # Create and register the response handler
            response_handler = WebSocketResponseHandler(self)
            
            response_handler_type = await response_handler.register(
                self.runtime,
                type="WEBSOCKET_RESPONSE_HANDLER",
                factory=lambda: WebSocketResponseHandler(self)
            )
            
            # Subscribe to the topics that send responses
            await self.runtime.add_subscription(
                TypeSubscription(topic_type=USER_TOPIC, agent_type=response_handler_type.type)
            )
            
            await self.runtime.add_subscription(
                TypeSubscription(topic_type=ENGINEER_AGENT_TOPIC, agent_type=response_handler_type.type)
            )
            
            self.logger.info("WebSocket response handler registered")
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to register response handler: {e}")
            return False
    
    async def send_response_to_client(self, session_id: str, response: str):
        """Send response back to WebSocket client"""
        client_info = self.connected_clients.get(session_id)
        if client_info:
            websocket = client_info["websocket"]
            try:
                await websocket.send(json.dumps({
                    "type": "message",
                    "content": response,
                    "timestamp": datetime.now().isoformat()
                }))
            except Exception as e:
                self.logger.error(f"Error sending response to {session_id}: {e}")
    
    async def send_error(self, session_id: str, error_message: str):
        """Send error message to client"""
        client_info = self.connected_clients.get(session_id)
        if client_info:
            websocket = client_info["websocket"]
            try:
                await websocket.send(json.dumps({
                    "type": "error",
                    "message": error_message
                }))
            except Exception as e:
                self.logger.error(f"Error sending error to {session_id}: {e}")
    
    async def start_server(self):
        """Start the WebSocket server"""
        if not await self.initialize_agent_system():
            self.logger.error("Failed to initialize agent system")
            return
        
        self.logger.info(f"Starting WebSocket server on {self.host}:{self.port}")
        
        # Use the correct websockets.serve syntax for newer versions
        async with websockets.serve(
            self.handle_client_connection, 
            self.host, 
            self.port
        ):
            self.logger.info(f"WebSocket server running on ws://{self.host}:{self.port}")
            print(f"""
🚀 WebSocket API Server Started
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📡 Server Address: ws://{self.host}:{self.port}
🔐 Authentication:
   👤 Customer: username="Customer", password="Customer@123"
   🔧 Engineer: username="Engineer", password="Engineer@123"

📝 Message Format:
   Authentication: {{"type": "auth", "username": "Customer", "password": "Customer@123"}}
   Chat Message: {{"type": "message", "content": "show me all audits"}}
   With File: {{"type": "message", "content": "generate code", "file": {{"name": "audit.txt", "content": "..."}}}}

🔄 Agent Routing:
   Customer → UserAgent → OrchestratorAgent → RetrievalAgent/ExecutionAgent
   Engineer → EngineerAgent → CodeGenerationAgent

Press Ctrl+C to stop the server
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
            """)
            
            # Keep server running
            await asyncio.Future()  # Run forever

async def main():
    """Main function"""
    server = WebSocketServer()
    try:
        await server.start_server()
    except KeyboardInterrupt:
        print("\n🛑 Server stopped by user")
    except Exception as e:
        print(f"❌ Server error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())