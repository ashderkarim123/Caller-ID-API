"""Pydantic schemas."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class CallerIDBase(BaseModel):
    caller_id: str = Field(..., examples=["18005551234"])
    carrier: Optional[str] = None
    area_code: Optional[str] = Field(default=None, max_length=10)
    daily_limit: Optional[int] = Field(default=None, ge=0)
    hourly_limit: Optional[int] = Field(default=None, ge=0)
    meta: Optional[Dict[str, Any]] = None


class CallerIDCreate(CallerIDBase):
    pass


class CallerIDResponse(CallerIDBase):
    last_used: Optional[datetime] = None

    class Config:
        from_attributes = True


class NextCIDResponse(BaseModel):
    caller_id: str
    expires_at: datetime
    campaign: str
    agent: str


class ReservationResponse(BaseModel):
    caller_id: str
    reserved_until: datetime
    agent: str
    campaign: str


class DashboardStats(BaseModel):
    total_caller_ids: int
    active_reservations: int
    last_requests: List[Dict[str, Any]]
    per_campaign_usage: Dict[str, int]
    caller_ids: List[CallerIDResponse]
    reservations: List[ReservationResponse]
