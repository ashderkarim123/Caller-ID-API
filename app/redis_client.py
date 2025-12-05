"""Redis client helper."""

from redis.asyncio import Redis

from .config import settings


redis_client = Redis.from_url(settings.redis_url, encoding="utf-8", decode_responses=True)


async def get_redis() -> Redis:
    """FastAPI dependency for redis connections."""
    return redis_client
