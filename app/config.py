"""
Configuration management for Caller-ID Rotation API
"""
import os
from typing import Optional
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # API Settings
    API_HOST: str = "127.0.0.1"
    API_PORT: int = 8000
    API_TITLE: str = "Caller-ID Rotation API"
    API_VERSION: str = "1.0.0"
    DEBUG: bool = False
    
    # Database Settings
    DB_HOST: str = "db"
    DB_PORT: int = 5432
    DB_USER: str = "callerid_user"
    DB_PASSWORD: str = "callerid_pass"
    DB_NAME: str = "callerid_db"
    
    @property
    def DATABASE_URL(self) -> str:
        """Construct PostgreSQL async connection URL"""
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
    
    # Redis Settings
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    
    # Security Settings
    ADMIN_TOKEN: str = "change-me-in-production"
    JWT_SECRET_KEY: str = "change-me-jwt-secret-key"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRATION_HOURS: int = 24
    
    # Caller-ID Settings
    RESERVATION_TTL_SECONDS: int = 300  # 5 minutes default reservation
    DEFAULT_DAILY_LIMIT: int = 1000
    DEFAULT_HOURLY_LIMIT: int = 100
    
    # Rate Limiting
    RATE_LIMIT_PER_AGENT: int = 100  # requests per minute per agent
    RATE_LIMIT_PER_IP: int = 200  # requests per minute per IP
    
    # Logging
    LOG_LEVEL: str = "INFO"
    LOG_FILE: Optional[str] = None
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()
