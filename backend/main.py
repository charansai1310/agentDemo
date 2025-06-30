"""
Main entry point for the Advanced Audit Management System
Complete system with all agents integrated
"""
import asyncio
import uuid
import sys
import os
import logging
from typing import Dict, Any, Optional
from datetime import datetime

# Add the current directory to the system path to ensure imports work correctly
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.append(current_dir)

from autogen_core import SingleThreadedAgentRuntime, TopicId, TypeSubscription
from autogen_ext.models.openai import OpenAIChatCompletionClient

from config import (
    CODE_GENERATION_AGENT_TOPIC,
    OPENAI_API_KEY, 
    OPENAI_MODEL,
    ORCHESTRATOR_AGENT_TOPIC,
    AUDIT_RETRIEVAL_AGENT_TOPIC,
    EXECUTE_AUDIT_AGENT_TOPIC,
    ENGINEER_AGENT_TOPIC,
    USER_TOPIC
)
from models import UserLogin, SystemStartup
from database import refresh_all_data

# Import all agents
from CiscoAgents.UserAgent import create_user_agent
from CiscoAgents.OrchestratorAgent import create_orchestrator_agent
from CiscoAgents.AuditRetrievalAgent import create_audit_retrieval_agent
from CiscoAgents.AuditExecutionAgent import create_audit_execution_agent
from CiscoAgents.EngineerAgent import create_engineer_agent
from CiscoAgents.CodeGenerationAgent import create_code_generation_agent


class AuditSystemRuntime:
    """
    Main runtime manager for the Advanced Audit Management System
    Handles agent registration, lifecycle, and system coordination
    """
    
    def __init__(self):
        self.runtime: Optional[SingleThreadedAgentRuntime] = None
        self.model_client: Optional[OpenAIChatCompletionClient] = None
        self.system_id = str(uuid.uuid4())
        self.startup_time = datetime.now()
        self.registered_agents: Dict[str, Any] = {}
        self.logger = self._setup_logging()
    
    def _setup_logging(self) -> logging.Logger:
        """Setup structured logging for the system"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.StreamHandler(),
                logging.FileHandler(f'audit_system_{datetime.now().strftime("%Y%m%d")}.log')
            ]
        )
        logging.getLogger('autogen_core').setLevel(logging.WARNING)
        logging.getLogger('autogen_core.events').setLevel(logging.WARNING)
        # Hide HTTP request logs from OpenAI client
        logging.getLogger('httpx').setLevel(logging.WARNING)
        return logging.getLogger('AuditSystem')
    
    async def validate_environment(self) -> bool:
        """Validate required environment variables and dependencies"""
        missing_vars = []
        
        if not OPENAI_API_KEY:
            missing_vars.append("OPENAI_API_KEY")
        
        try:
            from config import DATABASE_CONFIG
            for key, value in DATABASE_CONFIG.items():
                if key != 'port' and not value:
                    missing_vars.append(f"PG_{key.upper()}")
        except ImportError:
            self.logger.warning("Database configuration not found")
        
        if missing_vars:
            self.logger.error("Missing required environment variables:")
            for var in missing_vars:
                self.logger.error(f"   • {var}")
            return False
        return True
    
    async def test_database_connection(self) -> bool:
        """Test database connectivity and load existing data"""
        try:
            from database import get_database_connection
            connection = get_database_connection()
            if connection:
                connection.close()                
                # Load existing data from database
                data_result = refresh_all_data()
                if data_result and data_result.get('metadata', {}).get('total_audits', 0) > 0:
                    pass
                else:
                    self.logger.warning("No audit data found in database")
                
                return True
            else:
                self.logger.error("Database connection failed")
                return False
        except Exception as e:
            self.logger.error(f"Database connection error: {e}")
            return False
    
    async def initialize_runtime(self) -> bool:
        """Initialize the agent runtime and model client"""
        try:
            self.runtime = SingleThreadedAgentRuntime()
            self.model_client = OpenAIChatCompletionClient(
                model=OPENAI_MODEL,
                api_key=OPENAI_API_KEY,
            )
            return True
            
        except Exception as e:
            self.logger.error(f"Runtime initialization failed: {e}")
            return False
    
    async def register_agent(self, agent_name: str, agent_topic: str, agent_factory, subscriptions: list = None) -> bool:
        """Generic agent registration with error handling"""
        try:            
            agent_type = await agent_factory().register(
                self.runtime,
                type=agent_topic,
                factory=agent_factory,
            )
            
            # Add default subscription
            await self.runtime.add_subscription(
                TypeSubscription(topic_type=agent_topic, agent_type=agent_type.type)
            )
            
            # Add additional subscriptions if provided
            if subscriptions:
                for subscription_topic in subscriptions:
                    await self.runtime.add_subscription(
                        TypeSubscription(topic_type=subscription_topic, agent_type=agent_type.type)
                    )
            
            self.registered_agents[agent_name] = {
                'type': agent_type,
                'topic': agent_topic,
                'registered_at': datetime.now()
            }
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to register {agent_name}: {e}")
            return False
    
    async def register_all_agents(self) -> bool:
        """Register all system agents"""
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
                'factory': lambda: create_engineer_agent(ORCHESTRATOR_AGENT_TOPIC)  # Integrated mode
            },
            {
                'name': 'Code Generation Agent',
                'topic': CODE_GENERATION_AGENT_TOPIC,
                'factory': lambda: create_code_generation_agent()
            }
        ]
        
        success_count = 0
        for agent_config in agents_config:
            if await self.register_agent(
                agent_config['name'],
                agent_config['topic'],
                agent_config['factory']
            ):
                success_count += 1
        
        total_agents = len(agents_config)
        return success_count == total_agents
    
    async def start_system(self) -> bool:
        """Start the audit system runtime"""
        try:    
            self.runtime.start()
            
            # Publish system startup message
            await self.runtime.publish_message(
                SystemStartup(system_id=self.system_id, startup_time=self.startup_time),
                topic_id=TopicId(ORCHESTRATOR_AGENT_TOPIC, source=self.system_id)
            )
            
            self.display_system_status()
            return True
            
        except Exception as e:
            self.logger.error(f"Failed to start system: {e}")
            return False
    
    def display_system_status(self):
        print(f"System ID: {self.system_id}")
        print(f"Started at: {self.startup_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    async def start_user_session(self):
        """Start a user session"""
        user_session_id = str(uuid.uuid4())
        await self.runtime.publish_message(
            UserLogin(), 
            topic_id=TopicId(USER_TOPIC, source=user_session_id)
        )
    
    async def run(self):
        """Main system execution loop"""
        try:
            if not await self.validate_environment():
                print("❌ Environment validation failed. Please check your configuration.")
                return False
            
            if not await self.test_database_connection():
                print("⚠️  Database connection issues detected. System will run with limited functionality.")
            
            if not await self.initialize_runtime():
                print("❌ Runtime initialization failed.")
                return False
            
            if not await self.register_all_agents():
                print("❌ Agent registration failed.")
                return False
            
            if not await self.start_system():
                print("❌ System startup failed.")
                return False
            
            # Start user session
            await self.start_user_session()
            await self.runtime.stop_when_idle()
            
        except KeyboardInterrupt:
            pass
        except Exception as e:
            self.logger.error(f"System error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            await self.cleanup()
    
    async def cleanup(self):
        """Clean up system resources"""        
        try:
            if self.model_client:
                await self.model_client.close()
                
            if self.runtime:
                # Any additional runtime cleanup if needed
                pass            
        except Exception as e:
            self.logger.error(f"Error during cleanup: {e}")

async def main():
    audit_system = AuditSystemRuntime()
    await audit_system.run()

if __name__ == "__main__":
    asyncio.run(main())