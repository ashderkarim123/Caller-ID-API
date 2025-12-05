from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, constr, field_validator


PhoneNumber = constr(pattern=r"^\+?\d{8,16}$")  # type: ignore[var-annotated]


class AddCallerIDRequest(BaseModel):
    caller_id: PhoneNumber
    carrier: str | None = None
    area_code: constr(min_length=3, max_length=6) | None = None  # type: ignore[var-annotated]
    daily_limit: int | None = Field(default=500, ge=1)
    hourly_limit: int | None = Field(default=50, ge=1)
    meta: dict[str, Any] | None = None

    @field_validator("caller_id")
    @classmethod
    def digits_only(cls, value: str) -> str:
        return "".join(filter(str.isdigit, value))


class CallerIDResponse(BaseModel):
    caller_id: str
    carrier: str | None
    area_code: str | None
    daily_limit: int
    hourly_limit: int
    last_used: datetime | None
    meta: dict[str, Any] | None


class NextCallerIDResponse(BaseModel):
    caller_id: str
    agent: str
    campaign: str
    destination: str
    area_code: str | None
    expires_at: datetime
    reservation_ttl: int
    limits: dict[str, int | None]
    rate_limit_remaining: int | None = None


class HealthResponse(BaseModel):
    status: str
    db: str
    redis: str
    timestamp: datetime
