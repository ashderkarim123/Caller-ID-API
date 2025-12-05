"""
Redis client for fast caller-ID reservation and caching
"""
import redis.asyncio as aioredis
from typing import Optional, List, Dict
import json
import logging
from datetime import datetime, timedelta

from app.config import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Async Redis client for caller-ID management"""
    
    def __init__(self):
        self.redis: Optional[aioredis.Redis] = None
    
    async def connect(self):
        """Initialize Redis connection"""
        try:
            self.redis = await aioredis.from_url(
                settings.redis_url,
                encoding="utf-8",
                decode_responses=True,
                max_connections=50
            )
            await self.redis.ping()
            logger.info("Redis connection established")
        except Exception as e:
            logger.error(f"Redis connection error: {e}")
            raise
    
    async def close(self):
        """Close Redis connection"""
        if self.redis:
            await self.redis.close()
            logger.info("Redis connection closed")
    
    # Reservation Management
    
    async def reserve_caller_id(self, caller_id: str, agent: str, campaign: str, 
                                destination: str, ttl: int = None) -> bool:
        """
        Reserve a caller-ID for a specific agent/campaign
        Returns True if reserved successfully, False if already reserved
        """
        if ttl is None:
            ttl = settings.DEFAULT_RESERVATION_TTL
        
        key = f"reservation:{caller_id}"
        
        # Use SETNX to atomically set if not exists
        reservation_data = {
            'caller_id': caller_id,
            'agent': agent,
            'campaign': campaign,
            'destination': destination,
            'reserved_at': datetime.utcnow().isoformat()
        }
        
        # Try to set with NX (only if not exists) and EX (expiration)
        success = await self.redis.set(
            key,
            json.dumps(reservation_data),
            nx=True,
            ex=ttl
        )
        
        if success:
            # Add to active reservations set
            await self.redis.sadd(f"active_reservations:{campaign}", caller_id)
            await self.redis.expire(f"active_reservations:{campaign}", ttl + 60)
            
            # Track agent reservations
            await self.redis.sadd(f"agent_reservations:{agent}", caller_id)
            await self.redis.expire(f"agent_reservations:{agent}", ttl + 60)
            
            logger.info(f"Reserved {caller_id} for agent {agent}, campaign {campaign}")
        
        return bool(success)
    
    async def release_reservation(self, caller_id: str) -> bool:
        """Release a caller-ID reservation"""
        key = f"reservation:{caller_id}"
        deleted = await self.redis.delete(key)
        
        if deleted:
            logger.info(f"Released reservation for {caller_id}")
        
        return bool(deleted)
    
    async def get_reservation(self, caller_id: str) -> Optional[Dict]:
        """Get reservation details for a caller-ID"""
        key = f"reservation:{caller_id}"
        data = await self.redis.get(key)
        
        if data:
            return json.loads(data)
        return None
    
    async def is_reserved(self, caller_id: str) -> bool:
        """Check if a caller-ID is currently reserved"""
        key = f"reservation:{caller_id}"
        exists = await self.redis.exists(key)
        return bool(exists)
    
    async def get_active_reservations(self, campaign: Optional[str] = None) -> List[str]:
        """Get list of currently reserved caller-IDs"""
        if campaign:
            return list(await self.redis.smembers(f"active_reservations:{campaign}"))
        
        # Get all reservation keys
        keys = await self.redis.keys("reservation:*")
        return [key.replace("reservation:", "") for key in keys]
    
    # Rate Limiting
    
    async def check_rate_limit(self, agent: str, limit: int = None, window: int = 60) -> bool:
        """
        Check if agent has exceeded rate limit
        Returns True if within limit, False if exceeded
        """
        if limit is None:
            limit = settings.DEFAULT_RATE_LIMIT_PER_AGENT
        
        key = f"rate_limit:{agent}"
        current = await self.redis.incr(key)
        
        if current == 1:
            # First request in window, set expiration
            await self.redis.expire(key, window)
        
        return current <= limit
    
    async def get_rate_limit_count(self, agent: str) -> int:
        """Get current rate limit count for agent"""
        key = f"rate_limit:{agent}"
        count = await self.redis.get(key)
        return int(count) if count else 0
    
    # Caller-ID Usage Tracking
    
    async def increment_usage(self, caller_id: str, period: str = "hourly"):
        """Increment usage counter for a caller-ID"""
        now = datetime.utcnow()
        
        if period == "hourly":
            key = f"usage:{caller_id}:{now.strftime('%Y%m%d%H')}"
            ttl = 3600  # 1 hour
        elif period == "daily":
            key = f"usage:{caller_id}:{now.strftime('%Y%m%d')}"
            ttl = 86400  # 24 hours
        else:
            raise ValueError(f"Invalid period: {period}")
        
        count = await self.redis.incr(key)
        
        if count == 1:
            await self.redis.expire(key, ttl)
        
        return count
    
    async def get_usage(self, caller_id: str, period: str = "hourly") -> int:
        """Get usage count for a caller-ID"""
        now = datetime.utcnow()
        
        if period == "hourly":
            key = f"usage:{caller_id}:{now.strftime('%Y%m%d%H')}"
        elif period == "daily":
            key = f"usage:{caller_id}:{now.strftime('%Y%m%d')}"
        else:
            raise ValueError(f"Invalid period: {period}")
        
        count = await self.redis.get(key)
        return int(count) if count else 0
    
    async def check_usage_limit(self, caller_id: str, hourly_limit: int, daily_limit: int) -> bool:
        """
        Check if caller-ID has exceeded usage limits
        Returns True if within limits, False if exceeded
        """
        hourly_usage = await self.get_usage(caller_id, "hourly")
        daily_usage = await self.get_usage(caller_id, "daily")
        
        return hourly_usage < hourly_limit and daily_usage < daily_limit
    
    # LRU Tracking
    
    async def update_lru(self, caller_id: str, timestamp: Optional[float] = None):
        """Update LRU score for a caller-ID (lower score = least recently used)"""
        if timestamp is None:
            timestamp = datetime.utcnow().timestamp()
        
        await self.redis.zadd("caller_id_lru", {caller_id: timestamp})
    
    async def get_least_recently_used(self, count: int = 10, area_code: Optional[str] = None) -> List[str]:
        """Get least recently used caller-IDs"""
        # For area code filtering, we'd need to maintain separate sorted sets
        # For now, return from main LRU set
        caller_ids = await self.redis.zrange("caller_id_lru", 0, count - 1)
        return list(caller_ids)
    
    # Health Check
    
    async def health_check(self) -> Dict:
        """Check Redis health"""
        try:
            await self.redis.ping()
            info = await self.redis.info()
            return {
                'status': 'healthy',
                'connected_clients': info.get('connected_clients', 0),
                'used_memory': info.get('used_memory_human', 'unknown'),
                'uptime_seconds': info.get('uptime_in_seconds', 0)
            }
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return {
                'status': 'unhealthy',
                'error': str(e)
            }
    
    # Cache Management
    
    async def cache_set(self, key: str, value: str, ttl: int = 300):
        """Set a cache value with TTL"""
        await self.redis.set(f"cache:{key}", value, ex=ttl)
    
    async def cache_get(self, key: str) -> Optional[str]:
        """Get a cache value"""
        return await self.redis.get(f"cache:{key}")
    
    async def cache_delete(self, key: str):
        """Delete a cache value"""
        await self.redis.delete(f"cache:{key}")


# Global Redis client instance
redis_client = RedisClient()
