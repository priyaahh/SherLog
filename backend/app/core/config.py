"""
Configuration management for SherLog FastAPI Backend
"""

from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Backend application settings loaded from environment variables"""
    
    PROJECT_NAME: str = "SherLog Backend"
    API_V1_STR: str = "/api/v1"
    DEBUG: bool = True
    
    # MongoDB Configuration
    MONGODB_URL: str = "mongodb://localhost:27017"
    DATABASE_NAME: str = "sherlog"
    
    # External AI Service
    AI_SERVICE_URL: str = "http://localhost:5000"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore"
    )


settings = Settings()
