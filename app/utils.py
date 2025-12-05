"""
Utility functions for caller-ID rotation logic
"""
from typing import Optional, List, Dict
from datetime import datetime, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, func
from app.models import CallerID, Reservation
from app.redis_client import redis_client
import logging

logger = logging.getLogger(__name__)


async def get_next_caller_id(
    db: AsyncSession,
    to_number: str,
    campaign: str,
    agent: str,
    area_code_preference: Optional[str] = None
) -> Optional[Dict]:
    """
    Get the next available caller-ID for a call
    
    Logic:
    1. Extract area code from to_number if not provided
    2. Filter caller-IDs by area code, active status, and limits
    3. Check Redis reservations to avoid conflicts
    4. Use LRU rotation to select caller-ID
    5. Reserve the caller-ID in Redis
    6. Update last_used timestamp
    
    Returns dict with caller_id and metadata, or None if none available
    """
    # Extract area code from to_number if needed
    if not area_code_preference and to_number:
        # Remove non-digits and get first 3 digits (area code)
        digits = ''.join(filter(str.isdigit, to_number))
        if len(digits) >= 3:
            area_code_preference = digits[:3]
    
    # Build query for available caller-IDs
    query = select(CallerID).where(
        and_(
            CallerID.is_active == 1,
            or_(
                CallerID.area_code == area_code_preference,
                area_code_preference.isdigit() == False  # If no area code, match all
            ) if area_code_preference else True
        )
    )
    
    result = await db.execute(query)
    caller_ids = result.scalars().all()
    
    if not caller_ids:
        logger.warning(f"No active caller-IDs found for area code {area_code_preference}")
        return None
    
    # Get LRU list from Redis
    lru_caller_ids = await redis_client.get_lru_caller_ids(
        area_code=area_code_preference,
        limit=len(caller_ids) * 2
    )
    
    # Filter caller-IDs by availability
    available_caller_ids = []
    
    for cid_obj in caller_ids:
        caller_id = cid_obj.caller_id
        
        # Check if reserved in Redis
        if await redis_client.is_reserved(caller_id):
            continue
        
        # Check daily limit
        daily_used = await redis_client.get_usage_count(caller_id, "daily")
        if daily_used >= cid_obj.daily_limit:
            continue
        
        # Check hourly limit
        hourly_used = await redis_client.get_usage_count(caller_id, "hourly")
        if hourly_used >= cid_obj.hourly_limit:
            continue
        
        available_caller_ids.append(cid_obj)
    
    if not available_caller_ids:
        logger.warning(f"No available caller-IDs after filtering limits and reservations")
        return None
    
    # Sort by LRU (prefer those in LRU list, oldest first)
    def lru_sort_key(cid_obj):
        try:
            idx = lru_caller_ids.index(cid_obj.caller_id)
            return (0, idx)  # In LRU list, use index
        except ValueError:
            return (1, 0)  # Not in LRU list, use last_used or total_uses
    
    # Sort: first by LRU presence, then by last_used or total_uses
    available_caller_ids.sort(key=lambda x: (
        0 if x.caller_id in lru_caller_ids else 1,
        lru_caller_ids.index(x.caller_id) if x.caller_id in lru_caller_ids else 0,
        x.last_used.timestamp() if x.last_used else 0,
        x.total_uses
    ))
    
    # Try to reserve the first available caller-ID
    selected_cid = None
    for cid_obj in available_caller_ids:
        caller_id = cid_obj.caller_id
        
        # Try to reserve
        if await redis_client.reserve_caller_id(
            caller_id=caller_id,
            agent=agent,
            campaign=campaign,
            to_number=to_number
        ):
            selected_cid = cid_obj
            break
    
    if not selected_cid:
        logger.warning("Failed to reserve any caller-ID (concurrency conflict)")
        return None
    
    # Update database
    now = datetime.utcnow()
    selected_cid.last_used = now
    selected_cid.total_uses += 1
    
    # Increment usage counters in Redis
    await redis_client.increment_usage_counter(selected_cid.caller_id, "hourly")
    await redis_client.increment_usage_counter(selected_cid.caller_id, "daily")
    
    # Add to LRU tracking
    await redis_client.add_to_lru(
        selected_cid.caller_id,
        selected_cid.area_code
    )
    
    await db.commit()
    
    return {
        "caller_id": selected_cid.caller_id,
        "carrier": selected_cid.carrier,
        "area_code": selected_cid.area_code,
        "meta": selected_cid.meta or {}
    }


async def validate_caller_id_limits(
    caller_id: str,
    daily_limit: int,
    hourly_limit: int
) -> Dict[str, bool]:
    """
    Validate if a caller-ID can be used based on limits
    Returns dict with 'available' boolean and 'reason' string
    """
    daily_used = await redis_client.get_usage_count(caller_id, "daily")
    hourly_used = await redis_client.get_usage_count(caller_id, "hourly")
    
    if daily_used >= daily_limit:
        return {
            "available": False,
            "reason": f"Daily limit reached ({daily_used}/{daily_limit})"
        }
    
    if hourly_used >= hourly_limit:
        return {
            "available": False,
            "reason": f"Hourly limit reached ({hourly_used}/{hourly_limit})"
        }
    
    return {
        "available": True,
        "reason": "Available"
    }


async def cleanup_expired_reservations(db: AsyncSession):
    """
    Clean up expired reservations from database
    """
    now = datetime.utcnow()
    
    query = select(Reservation).where(
        Reservation.reserved_until < now
    )
    
    result = await db.execute(query)
    expired = result.scalars().all()
    
    for reservation in expired:
        await db.delete(reservation)
    
    await db.commit()
    
    return len(expired)
