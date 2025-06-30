"""
Models for the Audit Management System
Using Pydantic models for autogen_core compatibility
FIXED: Added session tracking fields for WebSocket support
"""

from typing import List, Optional, Any
from pydantic import BaseModel

class UserTask(BaseModel):
    """User task with conversation context"""
    context: List[Any]
    intent: Optional[str] = None   # optional string, default None
    action: Optional[str] = None
    original_message: str = None
    client_session_id: str = ""  # ✅ ADDED: Track WebSocket session

class AgentResponse(BaseModel):
    """Response from any agent back to user"""
    context: List[Any]
    reply_to_topic_type: str
    results: Optional[dict] = None  # ✅ ADDED: For additional data
    client_session_id: str = ""  # ✅ ADDED: Track WebSocket session

class EngineerTask(BaseModel):
    """Task message sent from orchestrator to engineer agent"""
    task_id: int
    user_id: str
    audit_description: str
    task_type: str = "create_new_audit"
    user_context: List[Any] = None

class EngineerNotification(BaseModel):
    """Notification from engineer to orchestrator about audit completion"""
    audit_name: str
    message: str
    task_id: int = None
    details: str = None

class EngineerLogin(BaseModel):
    """Message to start engineer interface"""
    engineer_id: str = None

class UserLogin(BaseModel):
    """Message to start user interface"""
    user_id: str = None

class SystemStartup(BaseModel):
    """Message to initialize the system"""
    startup_mode: str = "full"

class CodeGenerationRequest(BaseModel):
    """Request for code generation"""
    mop_content: str
    mop_filename: str
    engineer_session_id: str
    generation_type: str = "initial"
    feedback: Optional[str] = None  # ✅ KEPT: For code refinement

class CodeGenerationResponse(BaseModel):
    """Response with generated code"""
    generated_code: str
    mop_filename: str
    session_id: str
    iteration_number: int
    status: str
    explanation: str

class CodeFeedback(BaseModel):
    session_id: str
    mop_filename: str
    action: str  
    feedback: Optional[str] = None
    audit_name: Optional[str] = None
    category: Optional[str] = None

class CodeApproval(BaseModel):
    """Approval message for generated code"""
    session_id: str
    mop_filename: str
    approved: bool
    engineer_notes: str = None