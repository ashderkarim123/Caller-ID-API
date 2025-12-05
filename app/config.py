"""Application configuration powered by environment variables."""

from functools import lru_cache
from typing import List, Optional

from pydantic import AnyUrl, Field, PostgresDsn, validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Central settings object."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="Caller-ID Rotation API")
    environment: str = Field(default="development")
    admin_api_token: str = Field(default="change-me", description="Static token for admin endpoints")
    allowed_admin_ips: Optional[str] = Field(
        default=None, description="Comma separated whitelist for admin endpoints"
    )

    postgres_host: str = Field(default="db")
    postgres_port: int = Field(default=5432)
    postgres_db: str = Field(default="callerid")
    postgres_user: str = Field(default="callerid")
    postgres_password: str = Field(default="callerid")

    redis_url: AnyUrl = Field(default="redis://redis:6379/0")

    reservation_ttl_seconds: int = Field(default=900, description="Reservation TTL in seconds")
    agent_rate_limit_per_minute: int = Field(default=60)
    default_daily_limit: int = Field(default=500)
    default_hourly_limit: int = Field(default=60)

    log_level: str = Field(default="INFO")

    @property
    def database_url(self) -> PostgresDsn:
        return PostgresDsn.build(
            scheme="postgresql+asyncpg",
            username=self.postgres_user,
            password=self.postgres_password,
            host=self.postgres_host,
            port=str(self.postgres_port),
            path=f"/{self.postgres_db}",
        )

    @validator("allowed_admin_ips")
    def _normalize_ips(cls, value: Optional[str]) -> Optional[str]:
        return value if value else None

    def admin_ip_list(self) -> List[str]:
        if not self.allowed_admin_ips:
            return []
        return [item.strip() for item in self.allowed_admin_ips.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""

    return Settings()


settings = get_settings()
