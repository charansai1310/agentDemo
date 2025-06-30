import os
from dotenv import load_dotenv

load_dotenv()

DATABASE_CONFIG = {
    "host": os.getenv("PGHOST"),
    "database": os.getenv("PGDATABASE"),
    "user": os.getenv("PGUSER"),
    "password": os.getenv("PGPASSWORD"),
    "port": 5432
}

# OpenAI Configuration
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
OPENAI_MODEL = "gpt-4o-mini"

INTENT_MODEL_PATH = "IntentClassifier/intent_classifier_model.pt"
INTENT_TRAINING_DATA_PATH = "datasets/intent_training_data.csv"


ORCHESTRATOR_AGENT_TOPIC = "OrchestratorAgent"
AUDIT_RETRIEVAL_AGENT_TOPIC = "AuditRetrievalAgent"
EXECUTE_AUDIT_AGENT_TOPIC = "ExecuteAuditAgent"
ENGINEER_AGENT_TOPIC = "EngineerAgent"
CODE_GENERATION_AGENT_TOPIC = "CodeGenerationAgent"
USER_TOPIC = "User"