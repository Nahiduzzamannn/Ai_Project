import os
from dotenv import load_dotenv, find_dotenv
from pydantic_settings import BaseSettings

# Load .env as early as possible
load_dotenv(find_dotenv())

class Settings(BaseSettings):
    APP_NAME: str = "AI PDF RAG Backend"
    API_V1_PREFIX: str = "/api/v1"
    
    # Load from environment with os.getenv for explicit control
    OPENAI_API_KEY: str | None = os.getenv("OPENAI_API_KEY")
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg2://postgres:12345@localhost:5432/AI_ML_project"
    )

    class Config:
        env_file = ".env"

settings = Settings()