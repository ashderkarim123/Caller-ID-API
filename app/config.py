from functools import lru_cache
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    app_name: str = "Caller ID Rotation API"
    environment: str = Field(default="production", description="Environment name")
    api_host: str = Field(default="0.0.0.0", description="Host FastAPI binds to")
    api_port: int = Field(default=8000, description="Port FastAPI listens on")
    database_url: str = Field(
        default="postgresql+asyncpg://cid_user:cid_password@db:5432/caller_ids",
        description="Async SQLAlchemy database URL",
    )
    redis_url: str = Field(default="redis://redis:6379/0", description="Redis connection URL")
    admin_token: str = Field(default="change-me", description="Static admin token for dashboard")
    jwt_secret: str = Field(default="change-me", description="Secret for admin JWT validation")
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    reservation_ttl_seconds: int = Field(default=300, description="Reservation lock lifetime in seconds")
    agent_rate_limit_per_min: int = Field(default=60, description="Allowed requests per agent per minute")
    caller_id_cooldown_seconds: int = Field(default=30, description="Minimum seconds between reusing the same caller ID")
    allowed_origins: List[str] = Field(default_factory=list, description="CORS allowed origins")
    ip_whitelist: List[str] = Field(default_factory=list, description="Optional ip whitelist for admin endpoints")
    request_log_limit: int = Field(default=200, description="Max entries kept for recent request log")
    preload_redis_on_startup: bool = Field(default=True, description="Populate Redis caches on startup")
    log_level: str = Field(default="INFO", description="Application log level")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    @field_validator("allowed_origins", "ip_whitelist", mode="before")
    @classmethod
    def _split_csv(cls, value):  # type: ignore[override]
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    """Return cached settings instance."""

    return Settings()
