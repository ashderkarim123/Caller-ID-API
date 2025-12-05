"""
Redis client for caller-ID reservations and caching
"""
import json
import aioredis
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class RedisClient:
    """Redis client wrapper for caller-ID operations"""
    
    def __init__(self):
        self.redis: Optional[aioredis.Redis] = None
        self._connection_string = None
    
    async def connect(self):
        """Connect to Redis"""
        if self.redis is None:
            if settings.REDIS_PASSWORD:
                self._connection_string = f"redis://:{settings.REDIS_PASSWORD}@{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
            else:
                self._connection_string = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/{settings.REDIS_DB}"
            
            self.redis = await aioredis.from_url(
                self._connection_string,
                encoding="utf-8",
                decode_responses=True,
                max_connections=50
            )
            logger.info(f"Connected to Redis at {settings.REDIS_HOST}:{settings.REDIS_PORT}")
    
    async def disconnect(self):
        """Disconnect from Redis"""
        if self.redis:
            await self.redis.close()
            self.redis = None
    
    async def reserve_caller_id(
        self,
        caller_id: str,
        agent: str,
        campaign: str,
        to_number: Optional[str] = None,
        ttl: int = None
    ) -> bool:
        """
        Reserve a caller-ID for a specific agent/campaign
        
        Returns True if reservation successful, False if already reserved
        """
        if not self.redis:
            await self.connect()
        
        ttl = ttl or settings.RESERVATION_TTL_SECONDS
        key = f"reservation:{caller_id}"
        
        # Try to set reservation (only if key doesn't exist)
        reservation_data = {
            "agent": agent,
            "campaign": campaign,
            "to_number": to_number or "",
            "reserved_at": datetime.utcnow().isoformat(),
            "reserved_until": (datetime.utcnow() + timedelta(seconds=ttl)).isoformat()
        }
        
        # Use SET with NX (only if not exists) and EX (expiration)
        result = await self.redis.set(
            key,
            json.dumps(reservation_data),
            nx=True,  # Only set if key doesn't exist
            ex=ttl    # Set expiration
        )
        
        return result is True
    
    async def release_caller_id(self, caller_id: str):
        """Release a caller-ID reservation"""
        if not self.redis:
            await self.connect()
        
        key = f"reservation:{caller_id}"
        await self.redis.delete(key)
    
    async def is_reserved(self, caller_id: str) -> bool:
        """Check if a caller-ID is currently reserved"""
        if not self.redis:
            await self.connect()
        
        key = f"reservation:{caller_id}"
        exists = await self.redis.exists(key)
        return exists > 0
    
    async def get_reservation_info(self, caller_id: str) -> Optional[Dict]:
        """Get reservation information for a caller-ID"""
        if not self.redis:
            await self.connect()
        
        key = f"reservation:{caller_id}"
        data = await self.redis.get(key)
        
        if data:
            return json.loads(data)
        return None
    
    async def get_all_reservations(self) -> List[Dict]:
        """Get all active reservations"""
        if not self.redis:
            await self.connect()
        
        keys = await self.redis.keys("reservation:*")
        reservations = []
        
        for key in keys:
            data = await self.redis.get(key)
            if data:
                reservation = json.loads(data)
                reservation["caller_id"] = key.replace("reservation:", "")
                reservations.append(reservation)
        
        return reservations
    
    async def increment_usage_counter(
        self,
        caller_id: str,
        period: str = "hourly"  # "hourly" or "daily"
    ) -> int:
        """
        Increment usage counter for a caller-ID
        Returns the new count
        """
        if not self.redis:
            await self.connect()
        
        now = datetime.utcnow()
        
        if period == "hourly":
            key = f"usage:hourly:{caller_id}:{now.strftime('%Y%m%d%H')}"
            ttl = 3600  # 1 hour
        else:  # daily
            key = f"usage:daily:{caller_id}:{now.strftime('%Y%m%d')}"
            ttl = 86400  # 24 hours
        
        count = await self.redis.incr(key)
        await self.redis.expire(key, ttl)
        
        return count
    
    async def get_usage_count(
        self,
        caller_id: str,
        period: str = "hourly"
    ) -> int:
        """Get current usage count for a caller-ID"""
        if not self.redis:
            await self.connect()
        
        now = datetime.utcnow()
        
        if period == "hourly":
            key = f"usage:hourly:{caller_id}:{now.strftime('%Y%m%d%H')}"
        else:  # daily
            key = f"usage:daily:{caller_id}:{now.strftime('%Y%m%d')}"
        
        count = await self.redis.get(key)
        return int(count) if count else 0
    
    async def add_to_lru(self, caller_id: str, area_code: Optional[str] = None):
        """Add caller-ID to LRU tracking"""
        if not self.redis:
            await self.connect()
        
        # Use sorted set for LRU tracking (score = timestamp)
        lru_key = f"lru:area:{area_code}" if area_code else "lru:all"
        timestamp = datetime.utcnow().timestamp()
        
        await self.redis.zadd(lru_key, {caller_id: timestamp})
    
    async def get_lru_caller_ids(
        self,
        area_code: Optional[str] = None,
        limit: int = 100
    ) -> List[str]:
        """
        Get least recently used caller-IDs (oldest first)
        """
        if not self.redis:
            await self.connect()
        
        lru_key = f"lru:area:{area_code}" if area_code else "lru:all"
        
        # Get caller-IDs sorted by score (timestamp) ascending (oldest first)
        caller_ids = await self.redis.zrange(lru_key, 0, limit - 1, withscores=False)
        
        return [cid for cid in caller_ids]


# Global Redis client instance
redis_client = RedisClient()
