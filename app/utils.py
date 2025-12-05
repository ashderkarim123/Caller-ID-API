from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, Request, status

from .config import Settings


ALL_AREA_CODE = "__all__"


def utc_now() -> datetime:
    return datetime.now(tz=UTC)


def normalize_phone(value: str) -> str:
    digits = "".join(ch for ch in value if ch.isdigit())
    if digits.startswith("1") and len(digits) > 10:
        return digits[-10:]
    return digits


def extract_area_code(phone: str) -> str | None:
    digits = normalize_phone(phone)
    if len(digits) >= 10:
        return digits[:3]
    if len(digits) >= 3:
        return digits[:3]
    return None


def redis_area_key(area_code: str | None) -> str:
    code = area_code or ALL_AREA_CODE
    return f"cid-lru:{code}"


def reservation_key(caller_id: str) -> str:
    return f"reservation:{caller_id}"


def agent_rate_limit_key(agent: str) -> str:
    return f"ratelimit:agent:{agent.lower()}"


def caller_usage_day_key(caller_id: str, day: str) -> str:
    return f"usage:day:{caller_id}:{day}"


def caller_usage_hour_key(caller_id: str, hour: str) -> str:
    return f"usage:hour:{caller_id}:{hour}"


def campaign_stats_hash(campaign: str) -> str:
    return f"campaign:stats:{campaign.lower()}"


def campaign_agent_set(campaign: str) -> str:
    return f"campaign:agents:{campaign.lower()}"


def campaign_registry_set() -> str:
    return "campaign:names"


def recent_requests_list() -> str:
    return "logs:recent_requests"


def serialize_json(data: Any) -> str:
    return json.dumps(data, default=str)


def client_ip_from_request(request: Request) -> str | None:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    if request.client:
        return request.client.host
    return None


def enforce_ip_whitelist(request: Request, settings: Settings) -> None:
    if not settings.ip_whitelist:
        return
    client_ip = client_ip_from_request(request)
    if client_ip not in settings.ip_whitelist:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="IP not allowed")
