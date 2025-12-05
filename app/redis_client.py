from __future__ import annotations

from typing import AsyncIterator

from redis import asyncio as aioredis

from .config import get_settings


redis_pool: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Return a shared Redis client instance."""

    global redis_pool
    if redis_pool is None:
        settings = get_settings()
        redis_pool = aioredis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
            health_check_interval=30,
        )
    return redis_pool


async def redis_dependency() -> AsyncIterator[aioredis.Redis]:
    """FastAPI dependency wrapper around the shared Redis connection."""

    yield await get_redis()
