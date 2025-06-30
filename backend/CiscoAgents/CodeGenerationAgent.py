"""
Code Generation Agent for creating Python audit scripts from MOP files
This agent works with the Conversational Engineer Agent to generate, refine, and save audit code
Updated to save to audits folder and insert into database
"""
import asyncio
import os
import uuid
import sys
import time
import re
from typing import Dict, List, Optional
from pathlib import Path

# Add the parent directory to the system path
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.append(parent_dir)

from autogen_core import (
    MessageContext,
    RoutedAgent,
    TopicId,
    message_handler,
    SingleThreadedAgentRuntime,
    TypeSubscription,
)
from autogen_core.models import (
    AssistantMessage,
    UserMessage,
    SystemMessage,
)
from autogen_ext.models.openai import OpenAIChatCompletionClient

# Import from parent directory (backend)
from models import CodeGenerationRequest, CodeGenerationResponse, CodeFeedback, CodeApproval
from tools import load_existing_audit_templates, validate_python_code
from database import get_database_connection
from config import CODE_GENERATION_AGENT_TOPIC, ENGINEER_AGENT_TOPIC, OPENAI_API_KEY, OPENAI_MODEL

class CodeGenerationAgent(RoutedAgent):
    """Code Generation Agent for creating Python audit scripts"""
    
    def __init__(self, description: str, agent_topic_type: str, engineer_topic_type: str):
        super().__init__(description)
        self._agent_topic_type = agent_topic_type
        self._engineer_topic_type = engineer_topic_type
        
        # Session management - stores active code generation sessions
        self._sessions = {}  # engineer_session_id -> {mop_filename -> session_data}
        
        # Initialize LLM client
        self._model_client = OpenAIChatCompletionClient(
            model=OPENAI_MODEL,
            api_key=OPENAI_API_KEY,
        )
        
        # Status tracking for conversational flow
        self._generation_status = {}  # session_id -> status info

    @message_handler
    async def handle_generation_request(self, message: CodeGenerationRequest, ctx: MessageContext) -> None:
        """Handle code generation requests from Conversational Engineer Agent"""
        print(f"\n🤖 Code Generation Agent: Received request")
        print(f"   📄 MOP File: {message.mop_filename}")
        print(f"   🔄 Type: {message.generation_type}")
        print(f"   👨‍💻 From: {message.engineer_session_id}")
        
        # Update status for conversational tracking
        self._generation_status[message.engineer_session_id] = {
            'current_mop': message.mop_filename,
            'status': 'processing',
            'start_time': time.time()
        }
        
        try:
            if message.generation_type == "initial":
                await self.generate_initial_code(message, ctx)
            elif message.generation_type == "refinement":
                await self.refine_existing_code(message, ctx)
            else:
                await self.send_error_response(message, "Unknown generation type", ctx)
                
        except Exception as e:
            print(f"🤖 Code Generation Agent: Error occurred - {e}")
            await self.send_error_response(message, str(e), ctx)

    @message_handler
    async def handle_code_feedback(self, message: CodeFeedback, ctx: MessageContext) -> None:
        """Handle feedback from Conversational Engineer on generated code"""
        print(f"\n🤖 Code Generation Agent: Processing feedback")
        print(f"   ⚡ Action: {message.action}")
        print(f"   📋 Session: {message.session_id}")
        print(f"   📄 MOP: {message.mop_filename}")
        
        if message.action == "refine":
            print(f"   💬 Feedback: {message.feedback}")
        elif message.action == "approve":
            print(f"   📝 Audit Name: {message.audit_name}")
            print(f"   🏷️ Category: {message.category}")
        
        try:
            if message.action == "approve":
                await self.approve_and_save_code(message, ctx)
            elif message.action == "refine":
                await self.handle_refinement_request(message, ctx)
            elif message.action == "reject":
                await self.reject_code(message, ctx)
            else:
                print(f"🤖 Code Generation Agent: Unknown feedback action: {message.action}")
                
        except Exception as e:
            print(f"🤖 Code Generation Agent: Error handling feedback - {e}")

    async def generate_initial_code(self, request: CodeGenerationRequest, ctx: MessageContext) -> None:
        """Generate initial audit code from MOP content"""
        print(f"🤖 Code Generation Agent: Generating initial code for {request.mop_filename}")
        print("   ⏳ This may take 10-30 seconds...")
        
        # Initialize session
        session_data = {
            'mop_content': request.mop_content,
            'mop_filename': request.mop_filename,
            'iterations': [],
            'conversation_history': [],
            'status': 'generating',
            'created_at': time.time(),
            'is_virtual_mop': self._is_virtual_mop(request.mop_filename)
        }
        
        # Store session
        if request.engineer_session_id not in self._sessions:
            self._sessions[request.engineer_session_id] = {}
        self._sessions[request.engineer_session_id][request.mop_filename] = session_data
        
        # Load audit templates
        templates = load_existing_audit_templates()
        
        # Generate code using LLM
        print("   🧠 Calling AI model for code generation...")
        generated_code = await self.call_llm_for_generation(
            request.mop_content, 
            request.mop_filename,
            templates,
            []  # No previous iterations for initial generation
        )
        
        # Validate generated code
        print("   ✅ Validating generated code...")
        is_valid, validation_message = validate_python_code(generated_code)
        
        if not is_valid:
            print(f"   ⚠️ Code validation failed: {validation_message}")
            print("   🔧 Attempting to fix issues...")
            # Try to fix common issues
            generated_code = await self.fix_code_issues(generated_code, validation_message, templates)
            is_valid, validation_message = validate_python_code(generated_code)
            
            if is_valid:
                print("   ✅ Code issues fixed successfully!")
            else:
                print(f"   ❌ Could not auto-fix issues: {validation_message}")
        
        # Store iteration
        iteration = {
            'code': generated_code,
            'iteration_number': 1,
            'timestamp': time.time(),
            'validation_status': is_valid,
            'validation_message': validation_message
        }
        session_data['iterations'].append(iteration)
        session_data['current_code'] = generated_code
        session_data['status'] = 'pending_review'
        
        # Create appropriate explanation
        if session_data['is_virtual_mop']:
            explanation = f"Generated audit code directly from your task description."
        else:
            explanation = f"Generated audit code from the MOP file: {request.mop_filename}"
        
        if is_valid:
            explanation += " ✅ Code validation passed."
        else:
            explanation += f" ⚠️ Code has validation issues: {validation_message}"
        
        # Send response to Engineer
        response = CodeGenerationResponse(
            generated_code=generated_code,
            iteration_number=1,
            explanation=explanation,
            session_id=request.engineer_session_id,
            mop_filename=request.mop_filename,
            status="generated" if is_valid else "validation_failed"
        )
        
        await self.send_response_to_engineer(response, ctx)
        
        # Update status
        self._generation_status[request.engineer_session_id]['status'] = 'completed'
        
        # Display locally
        print(f"🤖 Code Generation Agent: ✅ Generation completed!")
        print(f"   📊 Validation: {'✅ Passed' if is_valid else '❌ Failed'}")
        print(f"   📏 Code Length: {len(generated_code)} characters")
        print(f"   📤 Response sent to Engineer Agent")

    async def refine_existing_code(self, request: CodeGenerationRequest, ctx: MessageContext) -> None:
        """Refine existing code based on feedback"""
        print(f"🤖 Code Generation Agent: Refining code for {request.mop_filename}")
        print("   ⏳ Processing your feedback...")
        
        # Get existing session
        session_data = self._sessions.get(request.engineer_session_id, {}).get(request.mop_filename)
        if not session_data:
            await self.send_error_response(request, "No existing code session found for refinement", ctx)
            return
        
        # Load templates
        templates = load_existing_audit_templates()
        
        # Generate refined code
        print("   🧠 Generating improved code based on feedback...")
        previous_iterations = session_data['iterations']
        refined_code = await self.call_llm_for_refinement(
            request.mop_content,
            request.mop_filename,
            templates,
            previous_iterations,
            request.feedback or "Please improve the code"
        )
        
        # Validate refined code
        print("   ✅ Validating refined code...")
        is_valid, validation_message = validate_python_code(refined_code)
        
        if not is_valid:
            print(f"   🔧 Attempting to fix validation issues...")
            refined_code = await self.fix_code_issues(refined_code, validation_message, templates)
            is_valid, validation_message = validate_python_code(refined_code)
        
        # Store iteration
        iteration_number = len(session_data['iterations']) + 1
        iteration = {
            'code': refined_code,
            'iteration_number': iteration_number,
            'timestamp': time.time(),
            'feedback_received': request.feedback,
            'validation_status': is_valid,
            'validation_message': validation_message
        }
        session_data['iterations'].append(iteration)
        session_data['current_code'] = refined_code
        
        # Send response
        explanation = f"Code refined based on your feedback (iteration {iteration_number})."
        if is_valid:
            explanation += " ✅ Validation passed."
        else:
            explanation += f" ⚠️ Validation issues: {validation_message}"
        
        response = CodeGenerationResponse(
            generated_code=refined_code,
            iteration_number=iteration_number,
            explanation=explanation,
            session_id=request.engineer_session_id,
            mop_filename=request.mop_filename,
            status="generated" if is_valid else "validation_failed"
        )
        
        await self.send_response_to_engineer(response, ctx)
        
        print(f"🤖 Code Generation Agent: ✅ Refinement completed (iteration {iteration_number})")

    def _is_virtual_mop(self, mop_filename: str) -> bool:
        """Check if this is a virtual MOP created from direct task description"""
        return mop_filename.startswith("direct_") or "virtual" in mop_filename.lower()

    def create_audit_filename(self, audit_name: str) -> str:
        """Create a clean filename from audit name"""
        # Remove special characters and spaces, keep only alphanumeric
        clean_name = re.sub(r'[^\w\s]', '', audit_name)
        # Replace spaces with empty string
        clean_name = clean_name.replace(' ', '')
        # Ensure it ends with .py
        if not clean_name.endswith('.py'):
            clean_name += '.py'
        return clean_name

    def save_audit_to_file(self, code: str, audit_name: str) -> tuple[bool, str]:
        """
        Save generated audit code to the audits folder
        
        Args:
            code: Generated Python code
            audit_name: Name of the audit (will be converted to filename)
            
        Returns:
            Tuple[bool, str]: (success, relative_path_or_error)
        """
        try:
            # Create filename from audit name
            filename = self.create_audit_filename(audit_name)
            
            # Get audits directory (outside of CiscoAgents folder)
            current_dir = Path(__file__).parent  # CiscoAgents folder
            audits_dir = current_dir.parent / "audits"  # ../audits
            
            # Ensure audits directory exists
            audits_dir.mkdir(exist_ok=True)
            
            # Full file path for writing
            file_path = audits_dir / filename
            
            # Add header comment
            header = f'''"""
Generated Audit Script
Audit Name: {audit_name}
Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}
Created by Code Generation Agent
"""

'''
            
            full_code = header + code
            
            # Save file
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(full_code)
            
            # Return relative path for database storage
            relative_path = f"audits/{filename}"
            return True, relative_path
            
        except Exception as e:
            return False, f"Error saving file: {e}"

    def insert_audit_to_database(self, audit_name: str, category: str, file_path: str, description: str = "") -> Optional[int]:
        """
        Insert new audit record into database
        
        Args:
            audit_name: Name of the audit
            category: Audit category
            file_path: Path to the saved audit file
            description: Optional description
            
        Returns:
            Optional[int]: audit_id if successful, None if failed
        """
        conn = get_database_connection()
        if not conn:
            print("   ❌ Failed to connect to database")
            return None
        
        cursor = None
        try:
            cursor = conn.cursor()
            
            # Insert audit record
            query = """
                INSERT INTO audits (audit_name, category, tags, description, device_categories, audit_path)
                VALUES (%s, %s, %s, %s, %s, %s)
                RETURNING audit_id
            """
            
            # Use default values as specified
            tags = ""  # Empty for now
            device_categories = "Server,Router,Switch,PC"  # All devices for now
            
            cursor.execute(query, (audit_name, category, tags, description, device_categories, file_path))
            
            audit_id = cursor.fetchone()[0]
            conn.commit()
            
            print(f"   💾 Audit inserted into database with ID: {audit_id}")
            return audit_id
            
        except Exception as e:
            print(f"   ❌ Error inserting audit into database: {e}")
            if conn:
                conn.rollback()
            return None
        finally:
            if cursor:
                cursor.close()
            conn.close()

    async def approve_and_save_code(self, feedback: CodeFeedback, ctx: MessageContext) -> None:
        """Approve and save the generated code with database integration"""
        print(f"🤖 Code Generation Agent: Saving approved code...")
        
        # Validate required fields
        if not feedback.audit_name or not feedback.category:
            print(f"   ❌ Missing required fields: audit_name={feedback.audit_name}, category={feedback.category}")
            return
        
        session_data = self._sessions.get(feedback.session_id, {}).get(feedback.mop_filename)
        if not session_data:
            print(f"   ❌ No session found for approval: {feedback.session_id}/{feedback.mop_filename}")
            return
        
        current_code = session_data.get('current_code')
        if not current_code:
            print("   ❌ No current code to save")
            return
        
        # Save the code to file
        print(f"   💾 Saving code to audits folder...")
        success, relative_path_or_error = self.save_audit_to_file(current_code, feedback.audit_name)
        
        if not success:
            print(f"🤖 Code Generation Agent: ❌ Error saving code: {relative_path_or_error}")
            return
        
        relative_path = relative_path_or_error
        print(f"   ✅ Code saved to: {relative_path}")
        
        # Insert into database
        print(f"   🗄️ Inserting audit into database...")
        description = f"Generated from {feedback.mop_filename}" if not session_data.get('is_virtual_mop', False) else "Generated from direct task request"
        
        audit_id = self.insert_audit_to_database(
            audit_name=feedback.audit_name,
            category=feedback.category,
            file_path=relative_path,  # Store relative path in database
            description=description
        )
        
        if audit_id:
            session_data['status'] = 'approved_and_saved'
            session_data['saved_path'] = relative_path
            session_data['audit_id'] = audit_id
            session_data['audit_name'] = feedback.audit_name
            session_data['category'] = feedback.category
            
            print(f"🤖 Code Generation Agent: ✅ Audit successfully created!")
            print(f"   📝 Audit Name: {feedback.audit_name}")
            print(f"   🏷️ Category: {feedback.category}")
            print(f"   🆔 Audit ID: {audit_id}")
            print(f"   📁 Database Path: {relative_path}")
        else:
            print(f"🤖 Code Generation Agent: ⚠️ Code saved to file but database insertion failed")

    async def handle_refinement_request(self, feedback: CodeFeedback, ctx: MessageContext) -> None:
        """Handle request for code refinement from conversational input"""
        print(f"🤖 Code Generation Agent: Processing refinement request...")
        
        session_data = self._sessions.get(feedback.session_id, {}).get(feedback.mop_filename)
        if not session_data:
            print(f"   ❌ No session found for refinement: {feedback.session_id}/{feedback.mop_filename}")
            return
        
        # Create refinement request
        refinement_request = CodeGenerationRequest(
            mop_content=session_data['mop_content'],
            mop_filename=feedback.mop_filename,
            engineer_session_id=feedback.session_id,
            generation_type="refinement",
            feedback=feedback.feedback
        )
        
        await self.refine_existing_code(refinement_request, ctx)

    async def reject_code(self, feedback: CodeFeedback, ctx: MessageContext) -> None:
        """Handle code rejection"""
        session_data = self._sessions.get(feedback.session_id, {}).get(feedback.mop_filename)
        if session_data:
            session_data['status'] = 'rejected'
        
        print(f"🤖 Code Generation Agent: Code rejected for {feedback.mop_filename}")
        print("   📝 Ready for new generation request when needed")

    async def call_llm_for_generation(self, mop_content: str, mop_filename: str, templates: List[Dict], previous_iterations: List) -> str:
        """Call LLM to generate audit code with enhanced prompting for conversational context"""
        
        # Build system prompt
        system_prompt = self.build_system_prompt_for_generation(templates)
        
        # Enhanced user prompt for better conversational context
        if self._is_virtual_mop(mop_filename):
            user_prompt = f"""Please generate a Python audit script based on this audit request:

AUDIT REQUEST: {mop_filename.replace('direct_', '').replace('_', ' ').replace('.txt', '')}

DESCRIPTION/REQUIREMENTS:
{mop_content}

IMPORTANT NOTES:
- This is a direct audit request (no formal MOP document)
- Extract the audit requirements from the description above
- Create practical audit commands based on the request intent
- Focus on the core functionality requested

CODING REQUIREMENTS:
1. Create a function named 'audit_[descriptive_name]' that performs the audit
2. Function should accept parameters: host, username, password, port=22
3. Return a list of tuples: [(command, output), ...]
4. Use paramiko for SSH connections
5. Include proper error handling
6. Add docstring with description and parameters
7. Follow the patterns shown in the template examples

Generate clean, working Python code that implements the audit requirements."""
        else:
            user_prompt = f"""Please generate a Python audit script based on this MOP (Method of Procedure):

MOP FILENAME: {mop_filename}

MOP CONTENT:
{mop_content}

REQUIREMENTS:
1. Create a function named 'audit_[descriptive_name]' that performs the audit
2. Function should accept parameters: host, username, password, port=22
3. Return a list of tuples: [(command, output), ...]
4. Use paramiko for SSH connections
5. Include proper error handling
6. Add docstring with description and parameters
7. Follow the patterns shown in the template examples

Generate clean, working Python code that implements the audit procedures described in the MOP."""

        messages = [
            SystemMessage(content=system_prompt, source="System"),
            UserMessage(content=user_prompt, source="User")
        ]
        
        try:
            result = await self._model_client.create(messages=messages, cancellation_token=None)
            return self.extract_code_from_response(result.content)
        except Exception as e:
            print(f"🤖 Code Generation Agent: Error calling LLM - {e}")
            return f"# Error generating code: {e}\n# Please try again or provide more specific requirements"

    async def call_llm_for_refinement(self, mop_content: str, mop_filename: str, templates: List[Dict], 
                                    previous_iterations: List, feedback: str) -> str:
        """Call LLM to refine existing code based on conversational feedback"""
        
        system_prompt = self.build_system_prompt_for_generation(templates)
        
        # Build conversation history with better context
        conversation_parts = []
        
        if self._is_virtual_mop(mop_filename):
            conversation_parts.append(f"Original Audit Request: {mop_content}")
        else:
            conversation_parts.append(f"Original MOP: {mop_content}")
        
        conversation_parts.append("\n--- PREVIOUS ITERATIONS ---")
        
        for iteration in previous_iterations:
            conversation_parts.append(f"\nIteration {iteration['iteration_number']}:")
            conversation_parts.append(f"Code:\n```python\n{iteration['code']}\n```")
            
            if iteration.get('validation_status') == False:
                conversation_parts.append(f"Validation Issues: {iteration.get('validation_message', 'Unknown')}")
            
            if 'feedback_received' in iteration:
                conversation_parts.append(f"Previous Feedback: {iteration['feedback_received']}")
        
        conversation_parts.append(f"\n--- CURRENT FEEDBACK ---")
        conversation_parts.append(f"Engineer's Request: {feedback}")
        conversation_parts.append("\nPlease generate an improved version of the audit code that addresses this feedback.")
        conversation_parts.append("Focus on the specific improvements requested while maintaining code quality.")
        
        user_prompt = "\n".join(conversation_parts)
        
        messages = [
            SystemMessage(content=system_prompt, source="System"),
            UserMessage(content=user_prompt, source="User")
        ]
        
        try:
            result = await self._model_client.create(messages=messages, cancellation_token=None)
            return self.extract_code_from_response(result.content)
        except Exception as e:
            print(f"🤖 Code Generation Agent: Error refining code - {e}")
            return f"# Error refining code: {e}\n# Please try again with different feedback"

    def build_system_prompt_for_generation(self, templates: List[Dict]) -> str:
        """Build system prompt with templates and guidelines"""
        prompt = """You are an expert Python developer specializing in network audit scripts for Cisco devices.

Your task is to generate Python audit scripts based on Method of Procedure (MOP) documents or direct audit requests.

CODING STANDARDS:
1. Use paramiko for SSH connections
2. Function name must start with 'audit_'
3. Always include proper error handling with try/except
4. Return format: List of tuples [(command, output), ...]
5. Include comprehensive docstrings
6. Use timeout values for SSH connections (default: 30 seconds)
7. Close SSH connections properly in finally blocks
8. Handle both successful outputs and errors gracefully
9. Use meaningful variable names
10. Add comments for complex operations

FUNCTION SIGNATURE TEMPLATE:
```python
def audit_[descriptive_name](host, username, password, port=22, timeout=30):
    \"\"\"
    Description of what this audit does
    
    Args:
        host (str): Device hostname or IP address
        username (str): SSH username
        password (str): SSH password  
        port (int): SSH port (default: 22)
        timeout (int): Connection timeout in seconds (default: 30)
    
    Returns:
        List[Tuple[str, str]]: List of (command, output) tuples
    \"\"\"
```

TEMPLATE EXAMPLES:
"""
        
        for i, template in enumerate(templates, 1):
            prompt += f"\n--- TEMPLATE {i}: {template['name']} ---\n"
            prompt += f"Description: {template['description']}\n"
            prompt += f"Code:\n{template['content']}\n"
        
        prompt += """

IMPORTANT GUIDELINES:
- Follow the exact patterns shown in templates
- Adapt the commands based on the requirements
- Include proper SSH connection handling with context managers when possible
- Add appropriate timeouts and error checking
- Generate clean, production-ready code
- Handle connection failures gracefully
- Return meaningful error messages in the output tuples
- Only return the Python code, no markdown formatting unless specifically requested
- Ensure code is immediately executable
"""
        
        return prompt

    def extract_code_from_response(self, response_content: str) -> str:
        """Extract Python code from LLM response with better handling"""
        content = response_content if isinstance(response_content, str) else str(response_content)
        
        # Look for code blocks
        if "```python" in content:
            start = content.find("```python") + 9
            end = content.find("```", start)
            if end != -1:
                code = content[start:end].strip()
                return code
        elif "```" in content:
            start = content.find("```") + 3
            end = content.find("```", start)
            if end != -1:
                code = content[start:end].strip()
                return code
        
        # If no code blocks, try to extract from def to end
        if "def audit_" in content:
            start = content.find("def audit_")
            # Find the end of the function (next def or end of string)
            remaining = content[start:]
            code = remaining.strip()
            return code
        
        # If no code blocks, return the whole content
        return content.strip()

    async def fix_code_issues(self, code: str, validation_error: str, templates: List[Dict]) -> str:
        """Attempt to fix common code issues with better error context"""
        print(f"   🔧 Attempting to fix: {validation_error}")
        
        fix_prompt = f"""Fix this Python code that has validation errors:

CURRENT CODE:
```python
{code}
```

VALIDATION ERROR:
{validation_error}

INSTRUCTIONS:
- Fix the specific error mentioned above
- Maintain the overall code structure and functionality
- Follow the coding standards from the templates
- Return only the corrected Python code
- Do not change the function purpose, only fix the syntax/logic issues

Please return the corrected code that will pass validation."""

        system_prompt = self.build_system_prompt_for_generation(templates)
        
        messages = [
            SystemMessage(content=system_prompt, source="System"),
            UserMessage(content=fix_prompt, source="User")
        ]
        
        try:
            result = await self._model_client.create(messages=messages, cancellation_token=None)
            fixed_code = self.extract_code_from_response(result.content)
            return fixed_code
        except Exception as e:
            print(f"   ❌ Error fixing code: {e}")
            return code  # Return original if fix fails

    async def send_response_to_engineer(self, response: CodeGenerationResponse, ctx: MessageContext) -> None:
        """Send response back to Conversational Engineer Agent"""
        try:
            await self.publish_message(
                response,
                topic_id=TopicId(self._engineer_topic_type, source=self.id.key),
            )
            print(f"   📤 Response sent successfully to Engineer Agent")
        except Exception as e:
            print(f"🤖 Code Generation Agent: ❌ Error sending response to engineer: {e}")

    async def send_error_response(self, request: CodeGenerationRequest, error_message: str, ctx: MessageContext) -> None:
        """Send error response to Conversational Engineer"""
        print(f"🤖 Code Generation Agent: Sending error response - {error_message}")
        
        response = CodeGenerationResponse(
            generated_code=f"# Error: {error_message}\n# Please try again or provide more details",
            iteration_number=0,
            explanation=f"Error generating code: {error_message}",
            session_id=request.engineer_session_id,
            mop_filename=request.mop_filename,
            status="error"
        )
        await self.send_response_to_engineer(response, ctx)

    def get_session_status(self, engineer_session_id: str) -> Dict:
        """Get status of all sessions for an engineer"""
        sessions = self._sessions.get(engineer_session_id, {})
        status = {}
        for mop_filename, session_data in sessions.items():
            status[mop_filename] = {
                'status': session_data['status'],
                'iterations': len(session_data['iterations']),
                'created_at': session_data['created_at'],
                'is_virtual_mop': session_data.get('is_virtual_mop', False),
                'audit_id': session_data.get('audit_id'),
                'audit_name': session_data.get('audit_name'),
                'category': session_data.get('category')
            }
        return status

def create_code_generation_agent():
    """Factory function to create a Code Generation Agent"""
    return CodeGenerationAgent(
        description="Code Generation agent for creating Python audit scripts from MOP files and direct requests.",
        agent_topic_type=CODE_GENERATION_AGENT_TOPIC,
        engineer_topic_type=ENGINEER_AGENT_TOPIC,
    )

# Main function for standalone execution (if needed)
async def main():
    """Main function for testing Code Generation Agent"""
    print("🤖 Code Generation Agent - Test Mode")
    print("This agent is designed to work with the Conversational Engineer Agent")
    print("Run the main system to use this agent properly")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🤖 Code Generation Agent test mode interrupted")
    except Exception as e:
        print(f"\n🤖 Error: {e}")
        import traceback
        traceback.print_exc()