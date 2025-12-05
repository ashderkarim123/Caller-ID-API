"""
Configuration settings for the Caller-ID Rotation API
"""
import os
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # API Settings
    API_TITLE: str = "VICIdial Caller-ID Rotation API"
    API_VERSION: str = "1.0.0"
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    DEBUG: bool = False
    
    # Database Settings
    POSTGRES_USER: str = "callerid_user"
    POSTGRES_PASSWORD: str = "change_this_password"
    POSTGRES_DB: str = "callerid_db"
    POSTGRES_HOST: str = "db"
    POSTGRES_PORT: int = 5432
    
    # Redis Settings
    REDIS_HOST: str = "redis"
    REDIS_PORT: int = 6379
    REDIS_DB: int = 0
    REDIS_PASSWORD: Optional[str] = None
    
    # Security Settings
    SECRET_KEY: str = "change_this_secret_key_to_something_secure"
    ADMIN_TOKEN: str = "change_this_admin_token"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 hours
    
    # Rate Limiting
    DEFAULT_RESERVATION_TTL: int = 300  # 5 minutes in seconds
    DEFAULT_RATE_LIMIT_PER_AGENT: int = 100  # requests per minute
    
    # Caller-ID Settings
    DEFAULT_HOURLY_LIMIT: int = 100
    DEFAULT_DAILY_LIMIT: int = 500
    
    # CORS Settings
    ALLOWED_ORIGINS: list = ["*"]
    
    @property
    def database_url(self) -> str:
        """Construct async PostgreSQL database URL"""
        return f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
    
    @property
    def redis_url(self) -> str:
        """Construct Redis URL"""
        if self.REDIS_PASSWORD:
            return f"redis://:{self.REDIS_PASSWORD}@{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
        return f"redis://{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Global settings instance
settings = Settings()
