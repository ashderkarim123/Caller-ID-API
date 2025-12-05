"""Utility helpers."""

import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, status

from .config import settings

PHONE_RE = re.compile(r"\D+")


def sanitize_number(raw_number: str) -> str:
    """Strip all non-digit chars."""
    return PHONE_RE.sub("", raw_number or "")


def extract_area_code(raw_number: str) -> Optional[str]:
    """Return NANP area code (first 3 digits) if available."""
    digits = sanitize_number(raw_number)
    if len(digits) >= 10:
        return digits[:3]
    if len(digits) >= 3:
        return digits[:3]
    return None


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def enforce_admin(auth_header: Optional[str], client_ip: Optional[str]) -> None:
    """Simple token/IP check for admin endpoints."""

    if auth_header != settings.admin_api_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid admin token"
        )

    allowed_ips = settings.admin_ip_list()
    if allowed_ips and client_ip not in allowed_ips:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin IP not whitelisted"
        )
