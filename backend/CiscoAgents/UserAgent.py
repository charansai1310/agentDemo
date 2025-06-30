"""
WebSocket-Compatible User Agent for handling user interactions
Modified to work with WebSocket connections instead of console interface
"""
from autogen_core import RoutedAgent, MessageContext, message_handler, TopicId
from autogen_core.models import UserMessage, AssistantMessage
from models import UserLogin, UserTask, AgentResponse
from config import ORCHESTRATOR_AGENT_TOPIC, USER_TOPIC

class WebSocketUserAgent(RoutedAgent):
    """Agent that handles user WebSocket interactions and routes through Orchestrator"""
    
    def __init__(self, description: str) -> None:
        super().__init__(description)
        self._user_topic_type = USER_TOPIC
        self._orchestrator_topic_type = ORCHESTRATOR_AGENT_TOPIC

    @message_handler
    async def handle_user_task(self, message: UserTask, ctx: MessageContext) -> None:
        """
        Handle user tasks from WebSocket and forward to Orchestrator
        
        Args:
            message: User task containing the conversation context
            ctx: Message context with session information
        """
        try:
            # Extract user message for logging
            user_content = ""
            if message.context:
                last_message = message.context[-1]
                if hasattr(last_message, 'content'):
                    user_content = last_message.content
            
            print(f"👤 UserAgent: Received WebSocket message: '{user_content}'")
            print(f"📤 UserAgent: Forwarding to Orchestrator...")
            
            # Forward the task directly to Orchestrator
            await self.publish_message(
                message,
                topic_id=TopicId(self._orchestrator_topic_type, source=ctx.topic_id.source),
            )
            
        except Exception as e:
            print(f"❌ UserAgent: Error processing WebSocket message: {e}")
            # Send error response back
            error_response = f"❌ Error processing your request: {str(e)}"
            message.context.append(
                AssistantMessage(content=error_response, source=self.id.type)
            )
            
            await self.publish_message(
                AgentResponse(context=message.context, reply_to_topic_type=self._user_topic_type),
                topic_id=TopicId(self._user_topic_type, source=ctx.topic_id.source),
            )

    @message_handler
    async def handle_agent_response(self, message: AgentResponse, ctx: MessageContext) -> None:
        """
        Handle responses from orchestrator and other agents
        Forward them back to WebSocket client via response handler
        """
        try:
            # Extract response content for logging
            response_content = ""
            if message.context and len(message.context) > 0:
                last_response = message.context[-1]
                if hasattr(last_response, 'content'):
                    response_content = last_response.content
            
            print(f"📨 UserAgent: Received response, forwarding to WebSocket client")
            print(f"📄 Response preview: {response_content[:100]}...")
            
            # Forward response back to WebSocket (will be caught by WebSocketResponseHandler)
            await self.publish_message(
                message,
                topic_id=TopicId(self._user_topic_type, source=ctx.topic_id.source),
            )
            
        except Exception as e:
            print(f"❌ UserAgent: Error handling response: {e}")

    @message_handler
    async def handle_user_login(self, message: UserLogin, ctx: MessageContext) -> None:
        """
        Handle user login - kept for backward compatibility with console mode
        For WebSocket mode, this won't be called since we skip login messages
        """
        print("👤 UserAgent: Login received (console mode)")
        print("⚠️  Note: This should not be called in WebSocket mode")


def create_websocket_user_agent() -> WebSocketUserAgent:
    """Factory function to create a WebSocket-compatible User Agent"""
    return WebSocketUserAgent(
        description="A WebSocket-compatible user agent that handles web interactions and routes requests through the Orchestrator Agent.",
    )

def create_user_agent() -> WebSocketUserAgent:
    """
    Factory function for compatibility with existing code
    Returns the WebSocket-compatible version
    """
    return create_websocket_user_agent()