import os
from dotenv import load_dotenv, find_dotenv
from pydantic_settings import BaseSettings

# Load .env as early as possible
load_dotenv(find_dotenv())

class Settings(BaseSettings):
    APP_NAME: str = "AI PDF RAG Backend"
    API_V1_PREFIX: str = "/api/v1"

    # Load from environment with os.getenv for explicit control
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://postgres:12345@localhost:5432/AI_ML_project"
    )

    # Local embedding model (fastembed, free, runs on CPU). Must match EMBEDDING_DIM.
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")

    # Elasticsearch (keyword / BM25 search). App falls back to Postgres if it's down.
    ELASTICSEARCH_URL: str = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
    ELASTICSEARCH_API_KEY: str | None = os.getenv("ELASTICSEARCH_API_KEY")
    ES_INDEX_PREFIX: str = os.getenv("ES_INDEX_PREFIX", "aiml")

    # AI agent: any OpenAI-compatible API. Default is Groq's free tier.
    LLM_API_KEY: str | None = os.getenv("LLM_API_KEY") or os.getenv("GROQ_API_KEY")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.groq.com/openai/v1")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "openai/gpt-oss-120b")
    # Max characters of chapter text sent to the LLM (keeps us under free-tier token limits)
    LLM_CONTEXT_CHARS: int = int(os.getenv("LLM_CONTEXT_CHARS", "12000"))

    class Config:
        env_file = ".env"
        extra = "ignore"

settings = Settings()

EMBEDDING_DIM = 384  # dimension of BAAI/bge-small-en-v1.5
