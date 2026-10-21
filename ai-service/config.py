"""
Configuration module for AIRS AI Service
Handles environment variables and application settings
"""

from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # API Configuration
    flask_env: str = "development"
    flask_host: str = "127.0.0.1"
    flask_debug: bool = False
    flask_port: int = 5000
    
    # LLM Configuration
    google_api_key: Optional[str] = None
    llm_model: str = "gemini-1.5-flash"
    llm_fallback_model: str = ""
    llm_temperature: float = 0.3
    
    # Vector Store (ChromaDB)
    chromadb_host: str = "localhost"
    chromadb_port: int = 8000
    chromadb_persist_dir: str = "./data/chromadb"
    
    # Backend Service
    backend_service_url: str = "http://localhost:8000"
    backend_api_key: Optional[str] = None
    
    # Redis (Optional)
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    
    # Logging
    log_level: str = "INFO"
    log_file: str = "./logs/airs.log"
    
    # RAG Configuration
    rag_chunk_size: int = 1000
    rag_chunk_overlap: int = 200
    rag_top_k: int = 5
    
    # Agent Configuration
    agent_timeout: int = 300
    agent_retries: int = 3
    
    class Config:
        env_file = ".env"
        case_sensitive = False


# Initialize settings
settings = Settings()
