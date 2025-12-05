"""Caller-ID rotation service layer."""

from __future__ import annotations

import json
from datetime import timedelta
from typing import Optional, Sequence

from fastapi import HTTPException, status
from redis.asyncio import Redis
from sqlalchemy import Select, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import settings
from ..models import CallerID, Reservation
from ..schemas import CallerIDCreate, CallerIDResponse, NextCIDResponse
from ..utils import extract_area_code, sanitize_number, utcnow

RESERVATION_KEY = "cid:reservation:{caller}"
LRU_KEY = "cid:lru:{scope}"
GLOBAL_SCOPE = "global"
DAILY_KEY = "cid:{caller}:daily"
HOURLY_KEY = "cid:{caller}:hourly"
AGENT_RATE_KEY = "cid:agent:{agent}:rate"
LAST_REQUESTS_KEY = "cid:last_requests"
CAMPAIGN_USAGE_KEY = "cid:campaign:{campaign}"


async def enforce_agent_rate_limit(redis: Redis, agent: str) -> None:
    """Limit per-agent request volume."""

    if not agent:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Agent required")
    key = AGENT_RATE_KEY.format(agent=agent)
    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, 60)
    if count > settings.agent_rate_limit_per_minute:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Agent rate limit exceeded",
        )


async def upsert_caller_id(
    session: AsyncSession, redis: Redis, payload: CallerIDCreate
) -> CallerIDResponse:
    """Insert or update a caller ID."""

    stmt: Select = select(CallerID).where(CallerID.caller_id == payload.caller_id)
    result = await session.execute(stmt)
    caller = result.scalar_one_or_none()

    if caller:
        caller.carrier = payload.carrier
        caller.area_code = payload.area_code
        caller.daily_limit = payload.daily_limit or settings.default_daily_limit
        caller.hourly_limit = payload.hourly_limit or settings.default_hourly_limit
        caller.meta = payload.meta
    else:
        caller = CallerID(
            caller_id=payload.caller_id,
            carrier=payload.carrier,
            area_code=payload.area_code,
            daily_limit=payload.daily_limit or settings.default_daily_limit,
            hourly_limit=payload.hourly_limit or settings.default_hourly_limit,
            meta=payload.meta,
        )
        session.add(caller)

    await session.commit()
    await session.refresh(caller)

    await ensure_lru(redis, caller.caller_id, caller.area_code)

    return CallerIDResponse.model_validate(caller)


async def ensure_lru(redis: Redis, caller_id: str, area_code: Optional[str]) -> None:
    """Ensure a caller ID exists in sorted sets for rotation."""

    score = utcnow().timestamp()
    global_key = LRU_KEY.format(scope=GLOBAL_SCOPE)
    await redis.zadd(global_key, {caller_id: score})
    if area_code:
        await redis.zadd(LRU_KEY.format(scope=area_code), {caller_id: score})


async def record_request(redis: Redis, payload: dict) -> None:
    """Store last N requests for dashboard."""

    await redis.lpush(LAST_REQUESTS_KEY, json.dumps(payload))
    await redis.ltrim(LAST_REQUESTS_KEY, 0, 49)


async def get_next_caller_id(
    session: AsyncSession,
    redis: Redis,
    destination: str,
    campaign: str,
    agent: str,
) -> NextCIDResponse:
    """Main allocation routine."""

    await enforce_agent_rate_limit(redis, agent)
    cleaned_destination = sanitize_number(destination)
    if not cleaned_destination:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid destination")

    area_code = extract_area_code(cleaned_destination)
    scopes = [GLOBAL_SCOPE]
    if area_code:
        scopes.insert(0, area_code)

    caller = await attempt_allocation(session, redis, scopes, campaign, agent)
    if not caller:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No caller IDs available")

    expires_at = utcnow() + timedelta(seconds=settings.reservation_ttl_seconds)
    reservation_key = RESERVATION_KEY.format(caller=caller.caller_id)
    reservation_payload = {
        "agent": agent,
        "campaign": campaign,
        "caller_id": caller.caller_id,
        "expires_at": expires_at.isoformat(),
    }
    await redis.set(reservation_key, json.dumps(reservation_payload), ex=settings.reservation_ttl_seconds)
    await redis.incr(CAMPAIGN_USAGE_KEY.format(campaign=campaign))

    await session.execute(
        update(CallerID)
        .where(CallerID.caller_id == caller.caller_id)
        .values(last_used=utcnow())
    )
    reservation = Reservation(
        caller_id=caller.caller_id,
        reserved_until=expires_at,
        agent=agent,
        campaign=campaign,
    )
    session.add(reservation)
    await session.commit()

    await record_request(
        redis,
        {
            "agent": agent,
            "campaign": campaign,
            "caller_id": caller.caller_id,
            "timestamp": utcnow().isoformat(),
        },
    )

    response = NextCIDResponse(
        caller_id=caller.caller_id,
        expires_at=expires_at,
        campaign=campaign,
        agent=agent,
    )
    return response


async def attempt_allocation(
    session: AsyncSession,
    redis: Redis,
    scopes: Sequence[str],
    campaign: str,
    agent: str,
) -> Optional[CallerID]:
    """Find a caller-id that satisfies rate limits and isn't reserved."""

    now_score = utcnow().timestamp()
    checked = set()
    for scope in scopes:
        key = LRU_KEY.format(scope=scope)
        caller_ids = await redis.zrange(key, 0, -1)
        for caller_id in caller_ids:
            if caller_id in checked:
                continue
            checked.add(caller_id)
            if await redis.exists(RESERVATION_KEY.format(caller=caller_id)):
                continue

            caller = await fetch_caller(session, caller_id)
            if not caller:
                await redis.zrem(key, caller_id)
                continue

            if not await within_limits(redis, caller.caller_id, caller.daily_limit, caller.hourly_limit):
                continue

            await redis.zadd(LRU_KEY.format(scope=GLOBAL_SCOPE), {caller.caller_id: now_score})
            if caller.area_code:
                await redis.zadd(LRU_KEY.format(scope=caller.area_code), {caller.caller_id: now_score})
            await increment_usage(redis, caller.caller_id, caller.daily_limit, caller.hourly_limit)
            return caller
    return None


async def fetch_caller(session: AsyncSession, caller_id: str) -> Optional[CallerID]:
    stmt = select(CallerID).where(CallerID.caller_id == caller_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def within_limits(
    redis: Redis, caller_id: str, daily_limit: Optional[int], hourly_limit: Optional[int]
) -> bool:
    if daily_limit:
        key = DAILY_KEY.format(caller=caller_id)
        value = await redis.get(key)
        current = int(value) if value else 0
        if current >= daily_limit:
            return False
    if hourly_limit:
        key = HOURLY_KEY.format(caller=caller_id)
        value = await redis.get(key)
        current = int(value) if value else 0
        if current >= hourly_limit:
            return False
    return True


async def increment_usage(
    redis: Redis, caller_id: str, daily_limit: Optional[int], hourly_limit: Optional[int]
) -> None:
    if daily_limit:
        key = DAILY_KEY.format(caller=caller_id)
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 86400)
    if hourly_limit:
        key = HOURLY_KEY.format(caller=caller_id)
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, 3600)
