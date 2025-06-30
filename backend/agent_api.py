"""
Agent REST API Gateway
Provides REST endpoints for the Multi-Agent System
Based on the working WebSocket implementation
"""

import asyncio
import uuid
import sys
import os
from typing import Dict, Any, Optional, List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn
from contextlib import asynccontextmanager

# Add current directory to path for imports
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

# Import your existing agent system (same as api_server.py)
from autogen_core import SingleThreadedAgentRuntime, TopicId, TypeSubscription, RoutedAgent, MessageContext, message_handler
from autogen_core.models import UserMessage
from autogen_ext.models.openai import OpenAIChatCompletionClient

from config import (
    OPENAI_API_KEY,
    OPENAI_MODEL,
    USER_TOPIC,
    ENGINEER_AGENT_TOPIC,
    ORCHESTRATOR_AGENT_TOPIC,
    AUDIT_RETRIEVAL_AGENT_TOPIC,
    EXECUTE_AUDIT_AGENT_TOPIC,
    CODE_GENERATION_AGENT_TOPIC
)
from models import UserTask, EngineerTask, AgentResponse

# Import your agent factories (same as api_server.py)
from CiscoAgents.UserAgent import create_user_agent
from CiscoAgents.OrchestratorAgent import create_orchestrator_agent
from CiscoAgents.AuditRetrievalAgent import create_audit_retrieval_agent
from CiscoAgents.AuditExecutionAgent import create_audit_execution_agent
from CiscoAgents.EngineerAgent import create_engineer_agent
from CiscoAgents.CodeGenerationAgent import create_code_generation_agent

# API Request/Response Models
class ChatRequest(BaseModel):
    message: str
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    context: Optional[List[Dict[str, Any]]] = None

class ChatResponse(BaseModel):
    response: str
    status: str
    agent: str
    session_id: str
    metadata: Optional[Dict[str, Any]] = None

class APIResponseHandler(RoutedAgent):
    """Response handler to capture agent responses for API clients"""
    
    def __init__(self, api_server):
        super().__init__("API Response Handler")
        self.api_server = api_server
    
    @message_handler
    async def handle_agent_response(self, message: AgentResponse, ctx: MessageContext) -> None:
        """Handle responses from any agent and route to API client"""
        try:
            session_id = ctx.topic_id.source
            print(f"[API Handler] Got response from topic {ctx.topic_id} for session {session_id}")
            
            # Only handle responses for active API requests
            if session_id in self.api_server.response_handlers:
                future = self.api_server.response_handlers[session_id]
                if not future.done():
                    print(f"[API Handler] Setting result for session {session_id}")
                    future.set_result(message)
                else:
                    print(f"[API Handler] Future already done for session {session_id}")
            else:
                print(f"[API Handler] No handler found for session {session_id}")
                
        except Exception as e:
            print(f"[API Handler] Error handling response: {e}")

class AgentAPIServer:
    """Manages agent runtime and API endpoints"""
    
    def __init__(self):
        self.runtime = None
        self.model_client = None
        self.response_handlers = {}  # Store response handlers by session
        
    async def initialize_agents(self):
        """Initialize the agent runtime and agents (same as api_server.py)"""
        try:
            # Initialize runtime and model client
            self.runtime = SingleThreadedAgentRuntime()
            self.model_client = OpenAIChatCompletionClient(
                model=OPENAI_MODEL,
                api_key=OPENAI_API_KEY,
            )
            
            # Register API Response Handler first
            await self.register_response_handler()
            
            # Register all agents (same as api_server.py)
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
                
                print(f"Registered {agent_config['name']}")
            
            # Start the runtime
            self.runtime.start()
            print("Agent system initialized successfully")
            
        except Exception as e:
            print(f"Failed to initialize agents: {e}")
            raise
    
    async def register_response_handler(self):
        """Register the API response handler agent"""
        try:
            # Create and register the response handler
            response_handler = APIResponseHandler(self)
            
            response_handler_type = await response_handler.register(
                self.runtime,
                type="API_RESPONSE_HANDLER",
                factory=lambda: APIResponseHandler(self)
            )
            
            # Subscribe to the topics that send responses (same as api_server.py)
            await self.runtime.add_subscription(
                TypeSubscription(topic_type=USER_TOPIC, agent_type=response_handler_type.type)
            )
            
            await self.runtime.add_subscription(
                TypeSubscription(topic_type=ENGINEER_AGENT_TOPIC, agent_type=response_handler_type.type)
            )
            
            print("API response handler registered")
            return True
            
        except Exception as e:
            print(f"Failed to register response handler: {e}")
            return False
    
    async def process_user_request(self, request: ChatRequest) -> ChatResponse:
        """Process request through UserAgent (same logic as api_server.py)"""
        session_id = request.session_id or str(uuid.uuid4())
        
        try:
            # Create response future for this session
            response_future = asyncio.Future()
            self.response_handlers[session_id] = response_future
            
            # Create message context (same as api_server.py)
            user_message = UserMessage(content=request.message, source="User")
            context = [user_message]
            
            # Create UserTask (same as api_server.py)
            task = UserTask(
                context=context,
                original_message=request.message,
                client_session_id=session_id
            )
            
            # Send to UserAgent (same as api_server.py)
            await self.runtime.publish_message(
                task,
                topic_id=TopicId(USER_TOPIC, source=session_id)
            )
            
            print(f"📤 Sent UserTask to USER_TOPIC for session {session_id}")
            
            # Wait for actual response from agent system
            try:
                response = await asyncio.wait_for(response_future, timeout=60.0)
                
                # Extract the actual response content
                response_content = "No response content"
                if hasattr(response, 'context') and response.context:
                    last_msg = response.context[-1]
                    if hasattr(last_msg, 'content'):
                        response_content = last_msg.content
                
                return ChatResponse(
                    response=response_content,
                    status="success",
                    agent="user_agent",
                    session_id=session_id,
                    metadata={"source": "agent_system"}
                )
                
            except asyncio.TimeoutError:
                raise HTTPException(status_code=408, detail="Agent system did not respond within 60 seconds")
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")
        
        finally:
            self.response_handlers.pop(session_id, None)
    
    async def process_engineer_request(self, request: ChatRequest) -> ChatResponse:
        """Process request through EngineerAgent (same logic as api_server.py)"""
        session_id = request.session_id or str(uuid.uuid4())
        
        try:
            # Create response future for this session
            response_future = asyncio.Future()
            self.response_handlers[session_id] = response_future
            
            # Create EngineerTask (same as api_server.py)
            task = EngineerTask(
                task_id=0,  # Placeholder
                user_id=session_id,
                audit_description=request.message,
                task_type="chat_request"
            )
            
            # Send to EngineerAgent (same as api_server.py)
            await self.runtime.publish_message(
                task,
                topic_id=TopicId(ENGINEER_AGENT_TOPIC, source=session_id)
            )
            
            print(f"📤 Sent EngineerTask to ENGINEER_AGENT_TOPIC for session {session_id}")
            
            # Wait for actual response from agent system
            try:
                response = await asyncio.wait_for(response_future, timeout=60.0)
                
                # Extract the actual response content
                response_content = "No response content"
                if hasattr(response, 'context') and response.context:
                    last_msg = response.context[-1]
                    if hasattr(last_msg, 'content'):
                        response_content = last_msg.content
                
                return ChatResponse(
                    response=response_content,
                    status="success",
                    agent="engineer_agent",
                    session_id=session_id,
                    metadata={"source": "agent_system"}
                )
                
            except asyncio.TimeoutError:
                raise HTTPException(status_code=408, detail="Agent system did not respond within 60 seconds")
            
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error processing request: {str(e)}")
        
        finally:
            self.response_handlers.pop(session_id, None)

# Global agent server instance
agent_server = AgentAPIServer()

# FastAPI app with lifespan management
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await agent_server.initialize_agents()
    yield
    # Shutdown
    if agent_server.runtime:
        agent_server.runtime.stop()
    if agent_server.model_client:
        await agent_server.model_client.close()

app = FastAPI(
    title="Multi-Agent System API",
    description="REST API for UserAgent and EngineerAgent with Swagger UI",
    version="1.0.0",
    docs_url="/docs",  # Swagger UI
    redoc_url="/redoc",  # ReDoc UI
    lifespan=lifespan
)

@app.post("/api/user-agent", response_model=ChatResponse)
async def user_agent_endpoint(request: ChatRequest):
    """
    Send message to UserAgent
    
    Process flow: UserAgent → OrchestrationAgent → (other agents) → UserAgent → Response
    """
    return await agent_server.process_user_request(request)

@app.post("/api/engineer-agent", response_model=ChatResponse)
async def engineer_agent_endpoint(request: ChatRequest):
    """
    Send message to EngineerAgent
    
    Process flow: EngineerAgent → OrchestrationAgent → (other agents) → EngineerAgent → Response  
    """
    return await agent_server.process_engineer_request(request)

if __name__ == "__main__":
    print("Starting Agent API Gateway...")
    print("Swagger UI will be available at: http://localhost:8001/docs")
    print("ReDoc UI will be available at: http://localhost:8001/redoc")
    
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=8001,
        log_level="info"
    )