"""
Orchestrator Agent for routing user requests to appropriate specialized agents using intent classification
"""
import json
import sys
import os
import uuid
from typing import List, Tuple, Dict, Any, Optional

from autogen_core import (
    MessageContext,
    RoutedAgent,
    TopicId,
    message_handler,
)
from autogen_core.models import (
    AssistantMessage,
    SystemMessage,
)
from autogen_ext.models.openai import OpenAIChatCompletionClient

# Fix import path for classifier
import sys
import os
parent_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if parent_dir not in sys.path:
    sys.path.append(parent_dir)
from IntentClassifier.Classifier import IntentClassifier

from models import UserTask, AgentResponse, EngineerTask, EngineerNotification

from config import (
    ORCHESTRATOR_AGENT_TOPIC, 
    USER_TOPIC, 
    AUDIT_RETRIEVAL_AGENT_TOPIC, 
    EXECUTE_AUDIT_AGENT_TOPIC,
    ENGINEER_AGENT_TOPIC,
    CODE_GENERATION_AGENT_TOPIC,
    OPENAI_API_KEY,
    OPENAI_MODEL
)

# Import the database insertion function
from database import insert_engineer_task

# Intent mapping configuration
INTENT_MAPPING = {
    "EXECUTE_AUDIT": EXECUTE_AUDIT_AGENT_TOPIC,
    "LIST_AUDITS": AUDIT_RETRIEVAL_AGENT_TOPIC,
    "GET_AUDIT_HISTORY": AUDIT_RETRIEVAL_AGENT_TOPIC,
    "GET_AUDIT_HISTORY_FILTERED": AUDIT_RETRIEVAL_AGENT_TOPIC,
    "AUDIT_RETRIEVAL_BY_CATEGORY": AUDIT_RETRIEVAL_AGENT_TOPIC,
    "ENGINEER_AUDIT": ENGINEER_AGENT_TOPIC,
    "GENERAL": "LLM_HANDLER"
}

# Confidence threshold for classifier
CONFIDENCE_THRESHOLD = 0.8000

def predict_intent(text: str, model_path: str = None) -> Tuple[str, float]:
    """
    Predict the intent of the given text using the intent classifier
    
    Args:
        text: User input text
        model_path: Optional path to classifier model
        
    Returns:
        Tuple containing intent label and confidence score
    """
    classifier = IntentClassifier()
    result = classifier.predict(text.lower())
    return result['label'], result['confidence']

def generate_user_session_id() -> str:
    """Generate a unique session ID for the user request"""
    return str(uuid.uuid4())[:8]

class OrchestratorAgent(RoutedAgent):
    """
    Orchestrator agent that routes user requests using intent classification
    and delegates to specialized agents
    """
    
    def __init__(
        self,
        description: str,
        agent_topic_type: str,
        user_topic_type: str,
        model_client: OpenAIChatCompletionClient = None,
    ) -> None:
        super().__init__(description)
        self._agent_topic_type = agent_topic_type
        self._user_topic_type = user_topic_type
        
        # Initialize LLM client for general/low-confidence queries
        if model_client is None:
            self._model_client = OpenAIChatCompletionClient(
                model=OPENAI_MODEL,
                api_key=OPENAI_API_KEY,
            )
        else:
            self._model_client = model_client
            
        # System messages for different LLM scenarios
        self._general_system_message = SystemMessage(
            content="""You are a helpful assistant for an Audit Management System. 
            Your primary goal is to guide users toward audit-related tasks while being conversational and helpful.
            
            The system specializes in:
            - **Audit Retrieval**: Listing, searching, and viewing available audits
            - **Audit Execution**: Running and executing specific audits
            - **Audit Engineering**: Creating custom audits for specific needs
            
            When users ask general questions:
            1. Answer their question helpfully and conversationally
            2. Gently guide them toward audit-related functionality
            3. Suggest relevant audit operations they might be interested in
            4. Ask if they'd like to see available audits or execute any audits
            
            Examples:
            - If they ask about weather, respond normally but suggest "Would you like to check system audits instead?"
            - If they ask about the system, explain audit capabilities and ask what they'd like to audit
            - Always be helpful but try to steer toward audit operations
            
            Keep responses concise and actionable."""
        )
        
        self._classification_system_message = SystemMessage(
            content="""You are a classification assistant for an Audit Management System.
            
            Your task is to classify user messages into one of these intents:
            - **LIST_AUDITS**: User wants to list, view, or browse all audits
            - **AUDIT_RETRIEVAL_BY_CATEGORY**: User wants to find audits by category (security, network, etc.)
            - **GET_AUDIT_HISTORY**: User wants to view past audit reports or history
            - **GET_AUDIT_HISTORY_FILTERED**: User wants filtered audit history (by date, device, etc.)
            - **EXECUTE_AUDIT**: User wants to run, execute, or perform an audit
            - **ENGINEER_AUDIT**: User wants to create, build, or develop a custom audit
            - **GENERAL**: Everything else (greetings, questions, casual conversation)
            
            Analyze the user's message and provide your classification with reasoning.
            
            Examples:
            - "show me all audits" → LIST_AUDITS
            - "what security audits do we have" → AUDIT_RETRIEVAL_BY_CATEGORY
            - "run audit 3" → EXECUTE_AUDIT
            - "show me audit results from yesterday" → GET_AUDIT_HISTORY_FILTERED
            - "create new audit" → ENGINEER_AUDIT
            - "hello" → GENERAL
            
            Respond with: "Based on the user message, I classify this as [intent] because [brief reasoning]."
            Then suggest what the system should do next."""
        )

    @message_handler
    async def handle_task(self, message: UserTask, ctx: MessageContext) -> None:
        """
        Handle incoming tasks using intent-based routing
        
        Args:
            message: User task containing the conversation context
            ctx: Message context
        """
        # Extract user message
        user_message = self._extract_user_message(message)

        if not user_message:
            # Send error response back to user
            error_response = "❌ No message content found. Please try again."
            await self._send_response_to_user(message, error_response)
            return

        # ALWAYS classify user input first using our built-in classifier
        predicted_intent, confidence = predict_intent(user_message)
        
        print(f"🎯 Classified intent: {predicted_intent} with confidence: {confidence}")
        
        # Decision logic based on confidence and intent
        if confidence >= CONFIDENCE_THRESHOLD and predicted_intent != "GENERAL":
            # High confidence + specific intent → Route directly to agent
            await self.route_to_agent(predicted_intent, message)
            
        elif predicted_intent == "GENERAL":
            # General intent → Use general LLM to guide toward audits
            llm_response = await self.handle_with_llm(user_message, message.context, "general")
            await self._send_response_to_user(message, llm_response)
            
        else:
            # Low confidence → Use classification LLM to determine intent and route
            llm_response = await self.handle_with_llm(user_message, message.context, "low_confidence")
            
            # Extract intent from LLM response
            clarified_intent = self.extract_intent_from_llm_response(llm_response)
            
            if clarified_intent != "GENERAL":
                # LLM identified a specific intent → Route directly to agent
                await self.route_to_agent(clarified_intent, message)
            else:
                # LLM couldn't clarify → Treat as general and respond to user
                fallback_response = await self.handle_with_llm(user_message, message.context, "general")
                await self._send_response_to_user(message, fallback_response)

    async def route_to_agent(self, intent: str, message: UserTask) -> None:
        """
        Route message to appropriate agent based on intent
        
        Args:
            intent: Predicted intent
            message: User task message
        """
        user_message = self._extract_user_message(message)
        
        if intent in ["LIST_AUDITS", "AUDIT_RETRIEVAL_BY_CATEGORY", "GET_AUDIT_HISTORY", "GET_AUDIT_HISTORY_FILTERED"]:
            # All retrieval intents go to the Audit Retrieval Agent
            target_topic = AUDIT_RETRIEVAL_AGENT_TOPIC
            
            # Set action based on intent
            if intent == "LIST_AUDITS":
                action = "list_audits"
            elif intent == "AUDIT_RETRIEVAL_BY_CATEGORY":
                action = "get_audits_by_category"
            elif intent == "GET_AUDIT_HISTORY":
                action = "get_audit_history"
            elif intent == "GET_AUDIT_HISTORY_FILTERED":
                action = "get_audit_history_filtered"
            
        elif intent == "EXECUTE_AUDIT":
            # Execute audit intent goes to the Audit Execution Agent
            target_topic = EXECUTE_AUDIT_AGENT_TOPIC
            action = "execute_audit"
            
        elif intent == "ENGINEER_AUDIT":
            # Handle engineer audit intent - INSERT TO DATABASE AND NOTIFY ENGINEER
            print(f"🔧 Routing engineering request to engineer: '{user_message}'")
            
            # Generate user session ID
            user_session_id = generate_user_session_id()
            
            # Insert directly into engineer_tasks table
            try:
                task_id = insert_engineer_task(
                    user_id=user_session_id,
                    request_description=user_message,
                    task_type="create_new_audit"
                )
                
                if task_id:
                    # Send success response to user
                    success_message = (
                        f"📤 Your audit creation request has been forwarded to our engineering team.\n"
                        f"⏳ Please wait for the engineer to process your request..."
                    )
                    await self._send_response_to_user(message, success_message)
                    print(f"✅ Engineer task {task_id} inserted successfully for user {user_session_id}")
                    
                    # DIRECT MESSAGE TO ENGINEER AGENT
                    try:
                        engineer_task = EngineerTask(
                            task_id=task_id,
                            user_id=user_session_id,
                            audit_description=user_message,
                            task_type="create_new_audit"
                        )
                        
                        await self.publish_message(
                            engineer_task,
                            topic_id=TopicId(ENGINEER_AGENT_TOPIC, source=self.id.key)
                        )
                        
                        print(f"📨 Direct message sent to EngineerAgent for task {task_id}")
                        
                    except Exception as e:
                        print(f"⚠️ Database insertion successful but engineer notification failed: {e}")
                        # Don't fail the whole operation if notification fails
                        
                else:
                    # Send error response to user
                    error_message = "❌ Sorry, there was an error processing your request. Please try again."
                    await self._send_response_to_user(message, error_message)
                    print(f"❌ Failed to insert engineer task for user {user_session_id}")
                    
            except Exception as e:
                print(f"❌ Error inserting engineer task: {e}")
                error_message = "❌ Sorry, there was an error processing your request. Please try again."
                await self._send_response_to_user(message, error_message)
            
            return  # Don't continue with normal delegation
            
        else:
            # Fallback - should not reach here due to logic above
            print(f"⚠️ Warning: Unhandled intent '{intent}' - falling back to general response")
            return

        # Create task for target agent (non-engineer cases)
        delegate_task = UserTask(context=message.context)
        delegate_task.intent = intent
        delegate_task.action = action
        delegate_task.original_message = user_message
        
        print(f"🚀 Routing to {target_topic} - Intent: {intent}, Action: {action}")
        
        # Send to target agent
        await self.publish_message(
            delegate_task, 
            topic_id=TopicId(target_topic, source=self.id.key)
        )

    @message_handler
    async def handle_agent_response(self, message: AgentResponse, ctx: MessageContext) -> None:
        """
        Handle responses from other agents and forward to user
        
        Args:
            message: Response from another agent
            ctx: Message context
        """
        print(f"📨 Forwarding agent response to user")
        
        # Forward the response to the user
        await self.publish_message(
            message,
            topic_id=TopicId(self._user_topic_type, source=self.id.key),
        )

    @message_handler
    async def handle_engineer_notification(self, message: EngineerNotification, ctx: MessageContext) -> None:
        """
        Handle notifications from Engineer Agent and route to user
        
        Args:
            message: Notification from Engineer Agent
            ctx: Message context
        """
        print(f"🎉 Received engineer notification: Audit '{message.audit_name}' {message.message}")
        
        # Create user-friendly notification message
        if message.message == "created":
            notification_text = f"✅ Great news! The audit '{message.audit_name}' has been successfully created!\n📋 You can now use this audit in your requests."
        elif message.message == "completed":
            notification_text = f"🎉 Audit '{message.audit_name}' has been completed!"
        elif message.message == "failed":
            notification_text = f"❌ Unfortunately, the audit '{message.audit_name}' creation failed. Please try again or contact support."
        else:
            notification_text = f"📢 Update: Audit '{message.audit_name}' {message.message}"
        
        # Add details if provided
        if hasattr(message, 'details') and message.details:
            notification_text += f"\n📝 Details: {message.details}"
        
        # Create context with the notification
        context = [AssistantMessage(content=notification_text, source=self.id.type)]
        
        # Send notification to user
        await self.publish_message(
            AgentResponse(
                context=context, 
                reply_to_topic_type=self._agent_topic_type
            ),
            topic_id=TopicId(self._user_topic_type, source=self.id.key),
        )

    async def _send_response_to_user(self, original_message: UserTask, response_content: str) -> None:
        """Helper method to send response back to user"""
        
        # Add response to conversation context
        original_message.context.append(
            AssistantMessage(content=response_content, source=self.id.type)
        )
        
        # Send response to user
        await self.publish_message(
            AgentResponse(context=original_message.context, reply_to_topic_type=self._agent_topic_type),
            topic_id=TopicId(self._user_topic_type, source=self.id.key),
        )

    async def handle_with_llm(self, user_message: str, message_context: List, scenario: str) -> str:
        """
        Handle queries with LLM using appropriate system message
        
        Args:
            user_message: The user's message
            message_context: Conversation context
            scenario: Either "general" or "low_confidence"
            
        Returns:
            str: LLM response for general, or intent for low_confidence
        """
        try:
            # Choose appropriate system message based on scenario
            if scenario == "general":
                system_msg = self._general_system_message
            elif scenario == "low_confidence":
                system_msg = self._classification_system_message
            else:
                system_msg = self._general_system_message  # Default fallback
            
            # Create messages for LLM
            llm_messages = [system_msg]
            
            # Add conversation context if available
            if message_context:
                llm_messages.extend(message_context)
            
            # Get LLM response
            llm_result = await self._model_client.create(
                messages=llm_messages,
                cancellation_token=None,
            )
            
            return llm_result.content if isinstance(llm_result.content, str) else str(llm_result.content)
            
        except Exception as e:
            print(f"❌ LLM processing error: {e}")
            return f"I apologize, but I'm having trouble processing your request right now. Please try again."

    def extract_intent_from_llm_response(self, llm_response: str) -> str:
        """
        Extract intent from LLM classification response
        
        Args:
            llm_response: Response from classification LLM
            
        Returns:
            str: Extracted intent or "GENERAL" if not found
        """
        response_lower = llm_response.lower()
        
        if "list_audits" in response_lower:
            return "LIST_AUDITS"
        elif "audit_retrieval_by_category" in response_lower:
            return "AUDIT_RETRIEVAL_BY_CATEGORY"
        elif "get_audit_history_filtered" in response_lower:
            return "GET_AUDIT_HISTORY_FILTERED"
        elif "get_audit_history" in response_lower:
            return "GET_AUDIT_HISTORY"
        elif "execute_audit" in response_lower:
            return "EXECUTE_AUDIT"
        elif "engineer_audit" in response_lower:
            return "ENGINEER_AUDIT"
        else:
            return "GENERAL"

    def _extract_user_message(self, message: UserTask) -> str:
        """Extract the latest user message from the context"""
        user_message = ""
        if message.context:
            last_message = message.context[-1]
            if hasattr(last_message, 'content'):
                user_message = last_message.content
        print(user_message)
        return user_message


def create_orchestrator_agent(model_client: OpenAIChatCompletionClient = None) -> OrchestratorAgent:
    """Factory function to create an Orchestrator Agent"""
    return OrchestratorAgent(
        description="An orchestrator agent that routes user requests using intent classification.",
        agent_topic_type=ORCHESTRATOR_AGENT_TOPIC,
        user_topic_type=USER_TOPIC,
        model_client=model_client,
    )

def set_confidence_threshold(threshold: float) -> None:
    """Helper function to change confidence threshold for testing"""
    global CONFIDENCE_THRESHOLD
    if 0.0 <= threshold <= 1.0:
        CONFIDENCE_THRESHOLD = threshold
        print(f"Confidence threshold changed to: {threshold}")
    else:
        print(f"Invalid threshold '{threshold}'. Must be between 0.0 and 1.0")

def get_confidence_threshold() -> float:
    """Get the current confidence threshold"""
    return CONFIDENCE_THRESHOLD