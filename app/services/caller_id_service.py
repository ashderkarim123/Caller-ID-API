from __future__ import annotations

import json
from datetime import timedelta
from typing import Any

from fastapi import HTTPException, status
from redis import asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from ..config import Settings
from ..models import CallerID, Reservation
from ..schemas import AddCallerIDRequest
from ..utils import (
    ALL_AREA_CODE,
    agent_rate_limit_key,
    caller_usage_day_key,
    caller_usage_hour_key,
    campaign_agent_set,
    campaign_registry_set,
    campaign_stats_hash,
    extract_area_code,
    normalize_phone,
    recent_requests_list,
    redis_area_key,
    reservation_key,
    serialize_json,
    utc_now,
)


class CallerIDService:
    """Business logic for managing caller IDs and reservations."""

    def __init__(self, session: AsyncSession, redis: aioredis.Redis, settings: Settings) -> None:
        self.session = session
        self.redis = redis
        self.settings = settings

    # ---------------------------------------------------------------------
    # Cache bootstrap
    # ---------------------------------------------------------------------
    async def preload_lru_cache(self) -> None:
        if not self.settings.preload_redis_on_startup:
            return
        exists = await self.redis.exists(redis_area_key(ALL_AREA_CODE))
        if exists:
            return
        result = await self.session.execute(select(CallerID))
        for caller in result.scalars():
            await self._sync_lru(caller)

    async def _sync_lru(self, caller: CallerID) -> None:
        score = (caller.last_used or utc_now()).timestamp()
        await self.redis.zadd(redis_area_key(caller.area_code), {caller.caller_id: score})
        await self.redis.zadd(redis_area_key(None), {caller.caller_id: score})

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------
    async def add_caller_id(self, payload: AddCallerIDRequest) -> CallerID:
        caller_id = normalize_phone(payload.caller_id)
        area_code = payload.area_code or extract_area_code(caller_id)
        exists = await self.session.get(CallerID, caller_id)
        if exists:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Caller ID already exists")
        caller = CallerID(
            caller_id=caller_id,
            carrier=payload.carrier,
            area_code=area_code,
            daily_limit=payload.daily_limit or 500,
            hourly_limit=payload.hourly_limit or 50,
            meta=payload.meta,
        )
        self.session.add(caller)
        try:
            await self.session.commit()
        except IntegrityError as exc:  # pragma: no cover - defensive
            await self.session.rollback()
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
        await self.session.refresh(caller)
        await self._sync_lru(caller)
        await self._log_request(
            endpoint="add-number",
            payload={
                "caller_id": caller.caller_id,
                "carrier": caller.carrier,
                "area_code": caller.area_code,
            },
        )
        return caller

    # ------------------------------------------------------------------
    # Allocation
    # ------------------------------------------------------------------
    async def get_next_caller_id(self, destination: str, campaign: str, agent: str) -> dict[str, Any]:
        destination_clean = normalize_phone(destination)
        area_code = extract_area_code(destination_clean)
        rate_limit_remaining = await self._enforce_agent_rate_limit(agent)
        candidate_ids = await self._candidate_pool(area_code)
        for caller_id in candidate_ids:
            allocation = await self._attempt_allocation(
                caller_id=caller_id,
                destination=destination_clean,
                campaign=campaign,
                agent=agent,
                area_code=area_code,
            )
            if allocation:
                allocation["rate_limit_remaining"] = rate_limit_remaining
                return allocation
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No caller IDs available")

    async def _candidate_pool(self, area_code: str | None) -> list[str]:
        primary = await self.redis.zrange(redis_area_key(area_code), 0, 99)
        fallback = await self.redis.zrange(redis_area_key(None), 0, 99)
        combined: list[str] = []
        seen: set[str] = set()
        for candidate in primary + fallback:
            if candidate not in seen:
                seen.add(candidate)
                combined.append(candidate)
        return combined

    async def _attempt_allocation(
        self,
        caller_id: str,
        destination: str,
        campaign: str,
        agent: str,
        area_code: str | None,
    ) -> dict[str, Any] | None:
        caller: CallerID | None = await self.session.get(CallerID, caller_id)
        if not caller:
            await self._purge_from_cache(caller_id, area_code)
            return None
        if not await self._caller_within_limits(caller):
            return None
        ttl_seconds = self.settings.reservation_ttl_seconds
        reserve_payload = serialize_json(
            {
                "caller_id": caller_id,
                "agent": agent,
                "campaign": campaign,
                "destination": destination,
            }
        )
        reserved = await self.redis.set(reservation_key(caller_id), reserve_payload, ex=ttl_seconds, nx=True)
        if not reserved:
            return None
        await self._increment_usage_counters(caller)
        await self._record_reservation(caller, agent, campaign, ttl_seconds)
        await self._log_request(
            endpoint="next-cid",
            payload={
                "agent": agent,
                "campaign": campaign,
                "caller_id": caller_id,
                "destination": destination,
            },
        )
        await self._track_campaign_stats(campaign, agent)
        await self._update_last_used(caller)
        expires_at = utc_now() + timedelta(seconds=ttl_seconds)
        return {
            "caller_id": caller.caller_id,
            "agent": agent,
            "campaign": campaign,
            "destination": destination,
            "area_code": caller.area_code,
            "expires_at": expires_at,
            "reservation_ttl": ttl_seconds,
            "limits": {
                "daily_limit": caller.daily_limit,
                "hourly_limit": caller.hourly_limit,
            },
        }

    async def _purge_from_cache(self, caller_id: str, area_code: str | None) -> None:
        await self.redis.zrem(redis_area_key(area_code), caller_id)
        await self.redis.zrem(redis_area_key(None), caller_id)

    async def _update_last_used(self, caller: CallerID) -> None:
        caller.last_used = utc_now()
        await self.session.merge(caller)
        await self.session.commit()
        await self.redis.zadd(redis_area_key(caller.area_code), {caller.caller_id: caller.last_used.timestamp()})
        await self.redis.zadd(redis_area_key(None), {caller.caller_id: caller.last_used.timestamp()})

    async def _caller_within_limits(self, caller: CallerID) -> bool:
        now = utc_now()
        day_key = caller_usage_day_key(caller.caller_id, now.strftime("%Y%m%d"))
        hour_key = caller_usage_hour_key(caller.caller_id, now.strftime("%Y%m%d%H"))
        daily_count = int(await self.redis.get(day_key) or 0)
        hourly_count = int(await self.redis.get(hour_key) or 0)
        if caller.daily_limit and daily_count >= caller.daily_limit:
            return False
        if caller.hourly_limit and hourly_count >= caller.hourly_limit:
            return False
        if caller.last_used:
            cooldown = (now - caller.last_used).total_seconds()
            if cooldown < self.settings.caller_id_cooldown_seconds:
                return False
        return True

    async def _increment_usage_counters(self, caller: CallerID) -> None:
        now = utc_now()
        day_key = caller_usage_day_key(caller.caller_id, now.strftime("%Y%m%d"))
        hour_key = caller_usage_hour_key(caller.caller_id, now.strftime("%Y%m%d%H"))
        await self.redis.incr(day_key)
        await self.redis.expire(day_key, 172800)
        await self.redis.incr(hour_key)
        await self.redis.expire(hour_key, 7200)

    async def _record_reservation(self, caller: CallerID, agent: str, campaign: str, ttl: int) -> None:
        expires_at = utc_now() + timedelta(seconds=ttl)
        reservation = Reservation(
            caller_id=caller.caller_id,
            reserved_until=expires_at,
            agent=agent,
            campaign=campaign,
        )
        self.session.add(reservation)
        await self.session.commit()

    async def _enforce_agent_rate_limit(self, agent: str) -> int | None:
        if self.settings.agent_rate_limit_per_min <= 0:
            return None
        key = agent_rate_limit_key(agent)
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, 60)
        if count > self.settings.agent_rate_limit_per_min:
            ttl = await self.redis.ttl(key)
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Agent rate limit exceeded. Retry in {max(ttl, 1)} seconds.",
            )
        remaining = max(self.settings.agent_rate_limit_per_min - count, 0)
        return remaining

    async def _log_request(self, endpoint: str, payload: dict[str, Any]) -> None:
        entry = {
            "ts": utc_now().isoformat(),
            "endpoint": endpoint,
            **payload,
        }
        list_key = recent_requests_list()
        await self.redis.lpush(list_key, json.dumps(entry))
        await self.redis.ltrim(list_key, 0, self.settings.request_log_limit - 1)

    async def _track_campaign_stats(self, campaign: str, agent: str) -> None:
        await self.redis.sadd(campaign_registry_set(), campaign.lower())
        await self.redis.hincrby(campaign_stats_hash(campaign), "calls", 1)
        await self.redis.sadd(campaign_agent_set(campaign), agent)

    # ------------------------------------------------------------------
    # Dashboard helpers
    # ------------------------------------------------------------------
    async def dashboard_snapshot(self) -> dict[str, Any]:
        caller_rows = (await self.session.execute(select(CallerID))).scalars().all()
        now = utc_now()
        caller_stats: list[dict[str, Any]] = []
        for caller in caller_rows:
            day_key = caller_usage_day_key(caller.caller_id, now.strftime("%Y%m%d"))
            hour_key = caller_usage_hour_key(caller.caller_id, now.strftime("%Y%m%d%H"))
            day_count = int(await self.redis.get(day_key) or 0)
            hour_count = int(await self.redis.get(hour_key) or 0)
            reservation_payload = await self.redis.get(reservation_key(caller.caller_id))
            caller_stats.append(
                {
                    "caller_id": caller.caller_id,
                    "carrier": caller.carrier,
                    "area_code": caller.area_code,
                    "daily_limit": caller.daily_limit,
                    "hourly_limit": caller.hourly_limit,
                    "last_used": caller.last_used,
                    "daily_count": day_count,
                    "hourly_count": hour_count,
                    "reserved": reservation_payload is not None,
                }
            )
        reservations = await self._active_reservations()
        recent_requests = await self._recent_requests()
        campaigns = await self._campaign_stats()
        return {
            "caller_ids": caller_stats,
            "reservations": reservations,
            "recent_requests": recent_requests,
            "campaigns": campaigns,
        }

    async def _active_reservations(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        cursor = 0
        while True:
            cursor, keys = await self.redis.scan(cursor=cursor, match="reservation:*", count=50)
            for key in keys:
                payload = await self.redis.get(key)
                if payload:
                    data = json.loads(payload)
                    ttl = await self.redis.ttl(key)
                    records.append({**data, "expires_in": ttl})
            cursor = int(cursor)
            if cursor == 0:
                break
        return records

    async def _recent_requests(self) -> list[dict[str, Any]]:
        items = await self.redis.lrange(recent_requests_list(), 0, self.settings.request_log_limit - 1)
        return [json.loads(item) for item in items]

    async def _campaign_stats(self) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        campaign_names = await self.redis.smembers(campaign_registry_set())
        for name in campaign_names:
            stats = await self.redis.hgetall(campaign_stats_hash(name))
            agent_count = await self.redis.scard(campaign_agent_set(name))
            entries.append(
                {
                    "campaign": name,
                    "total_calls": int(stats.get("calls", 0)),
                    "unique_agents": agent_count,
                }
            )
        return entries
