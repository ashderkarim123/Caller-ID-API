"""
Main FastAPI application for Caller-ID Rotation API
"""
from fastapi import FastAPI, Depends, HTTPException, Request, Query, status
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, and_, or_, delete
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import logging
import asyncio

from app.config import settings
from app.models import CallerID, Reservation, APILog
from app.db import init_db, get_db, close_db
from app.redis_client import redis_client
from app.utils import (
    verify_admin_token, extract_area_code, validate_phone_number,
    sanitize_input, log_api_request, Timer, security
)

# Configure logging
logging.basicConfig(
    level=logging.INFO if not settings.DEBUG else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown"""
    # Startup
    logger.info("Starting Caller-ID Rotation API...")
    await init_db()
    await redis_client.connect()
    logger.info("API started successfully")
    
    yield
    
    # Shutdown
    logger.info("Shutting down API...")
    await redis_client.close()
    await close_db()
    logger.info("API shutdown complete")


# Create FastAPI app
app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files and templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


# ============= API Endpoints =============

@app.get("/health")
async def health_check(db: AsyncSession = Depends(get_db)):
    """Health check endpoint"""
    try:
        # Check database connection
        await db.execute(select(func.count()).select_from(CallerID))
        db_status = "healthy"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = "unhealthy"
    
    # Check Redis connection
    redis_status = await redis_client.health_check()
    
    return {
        "status": "healthy" if db_status == "healthy" and redis_status["status"] == "healthy" else "degraded",
        "timestamp": datetime.utcnow().isoformat(),
        "database": db_status,
        "redis": redis_status,
        "version": settings.API_VERSION
    }


@app.get("/next-cid")
async def get_next_caller_id(
    request: Request,
    to: str = Query(..., description="Destination phone number"),
    campaign: str = Query(..., description="Campaign name"),
    agent: str = Query(..., description="Agent name"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get next available caller-ID for a call
    Main endpoint used by VICIdial dialplan
    """
    timer = Timer()
    timer.__enter__()
    
    try:
        # Sanitize inputs
        to = sanitize_input(to, 20)
        campaign = sanitize_input(campaign, 100)
        agent = sanitize_input(agent, 100)
        
        # Validate destination number
        if not validate_phone_number(to):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid destination phone number"
            )
        
        # Check rate limit for agent
        if not await redis_client.check_rate_limit(agent):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Rate limit exceeded for agent {agent}"
            )
        
        # Extract area code from destination
        area_code = extract_area_code(to)
        
        # Find available caller-ID
        caller_id_record = await find_available_caller_id(db, area_code, campaign, agent)
        
        if not caller_id_record:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No available caller-IDs at this time"
            )
        
        # Reserve the caller-ID in Redis
        reserved = await redis_client.reserve_caller_id(
            caller_id_record.caller_id,
            agent,
            campaign,
            to
        )
        
        if not reserved:
            # Already reserved, try to find another one
            logger.warning(f"Caller-ID {caller_id_record.caller_id} already reserved, retrying...")
            caller_id_record = await find_available_caller_id(db, area_code, campaign, agent, exclude=[caller_id_record.caller_id])
            
            if caller_id_record:
                reserved = await redis_client.reserve_caller_id(
                    caller_id_record.caller_id,
                    agent,
                    campaign,
                    to
                )
        
        if not caller_id_record or not reserved:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No available caller-IDs at this time"
            )
        
        # Update last_used timestamp
        await db.execute(
            update(CallerID)
            .where(CallerID.caller_id == caller_id_record.caller_id)
            .values(last_used=datetime.utcnow())
        )
        
        # Create reservation record in database
        reservation = Reservation(
            caller_id=caller_id_record.caller_id,
            reserved_until=datetime.utcnow() + timedelta(seconds=settings.DEFAULT_RESERVATION_TTL),
            agent=agent,
            campaign=campaign,
            destination=to
        )
        db.add(reservation)
        
        # Increment usage counters in Redis
        await redis_client.increment_usage(caller_id_record.caller_id, "hourly")
        await redis_client.increment_usage(caller_id_record.caller_id, "daily")
        
        # Update LRU
        await redis_client.update_lru(caller_id_record.caller_id)
        
        await db.commit()
        
        timer.__exit__()
        
        # Log API request
        await log_api_request(
            db,
            endpoint="/next-cid",
            method="GET",
            agent=agent,
            campaign=campaign,
            caller_id_allocated=caller_id_record.caller_id,
            destination=to,
            response_time_ms=timer.elapsed_ms,
            status_code=200
        )
        
        logger.info(f"Allocated {caller_id_record.caller_id} to agent {agent} for campaign {campaign}")
        
        return {
            "success": True,
            "caller_id": caller_id_record.caller_id,
            "area_code": caller_id_record.area_code,
            "carrier": caller_id_record.carrier,
            "reserved_for": settings.DEFAULT_RESERVATION_TTL,
            "destination": to,
            "agent": agent,
            "campaign": campaign
        }
    
    except HTTPException:
        raise
    except Exception as e:
        timer.__exit__()
        logger.error(f"Error in get_next_caller_id: {e}", exc_info=True)
        
        await log_api_request(
            db,
            endpoint="/next-cid",
            method="GET",
            agent=agent,
            campaign=campaign,
            destination=to,
            response_time_ms=timer.elapsed_ms,
            status_code=500,
            error_message=str(e)
        )
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


async def find_available_caller_id(
    db: AsyncSession,
    area_code: Optional[str],
    campaign: str,
    agent: str,
    exclude: List[str] = None
) -> Optional[CallerID]:
    """
    Find an available caller-ID using LRU strategy
    Prioritizes area code matching if available
    """
    exclude = exclude or []
    
    # Build query for available caller-IDs
    query = select(CallerID).where(
        and_(
            CallerID.is_active == 1,
            CallerID.caller_id.notin_(exclude) if exclude else True
        )
    )
    
    # Try to match area code first
    if area_code:
        area_query = query.where(CallerID.area_code == area_code).order_by(
            CallerID.last_used.asc().nullsfirst()
        ).limit(10)
        
        result = await db.execute(area_query)
        candidates = result.scalars().all()
    else:
        candidates = []
    
    # If no area code matches, get any available
    if not candidates:
        fallback_query = query.order_by(
            CallerID.last_used.asc().nullsfirst()
        ).limit(10)
        
        result = await db.execute(fallback_query)
        candidates = result.scalars().all()
    
    # Filter out reserved and limit-exceeded caller-IDs
    for candidate in candidates:
        # Check if reserved in Redis
        if await redis_client.is_reserved(candidate.caller_id):
            continue
        
        # Check usage limits
        if not await redis_client.check_usage_limit(
            candidate.caller_id,
            candidate.hourly_limit,
            candidate.daily_limit
        ):
            continue
        
        return candidate
    
    return None


@app.post("/add-number")
async def add_caller_id(
    request: Request,
    caller_id: str = Query(..., description="Caller-ID to add"),
    carrier: Optional[str] = Query(None, description="Carrier name"),
    area_code: Optional[str] = Query(None, description="Area code"),
    daily_limit: Optional[int] = Query(None, description="Daily usage limit"),
    hourly_limit: Optional[int] = Query(None, description="Hourly usage limit"),
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """
    Add a new caller-ID to the system
    Requires admin token
    """
    # Verify admin token
    verify_admin_token(credentials)
    
    try:
        # Sanitize inputs
        caller_id = sanitize_input(caller_id, 20)
        carrier = sanitize_input(carrier, 100) if carrier else None
        area_code = sanitize_input(area_code, 10) if area_code else extract_area_code(caller_id)
        
        # Validate caller-ID format
        if not validate_phone_number(caller_id):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid caller-ID format"
            )
        
        # Check if caller-ID already exists
        result = await db.execute(
            select(CallerID).where(CallerID.caller_id == caller_id)
        )
        existing = result.scalar_one_or_none()
        
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Caller-ID {caller_id} already exists"
            )
        
        # Create new caller-ID record
        new_caller_id = CallerID(
            caller_id=caller_id,
            carrier=carrier,
            area_code=area_code,
            daily_limit=daily_limit or settings.DEFAULT_DAILY_LIMIT,
            hourly_limit=hourly_limit or settings.DEFAULT_HOURLY_LIMIT,
            is_active=1
        )
        
        db.add(new_caller_id)
        await db.commit()
        await db.refresh(new_caller_id)
        
        # Initialize in Redis LRU with old timestamp (least recently used)
        await redis_client.update_lru(caller_id, 0)
        
        logger.info(f"Added new caller-ID: {caller_id}")
        
        return {
            "success": True,
            "message": f"Caller-ID {caller_id} added successfully",
            "data": new_caller_id.to_dict()
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding caller-ID: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin dashboard showing caller-ID stats and usage
    Requires admin token
    """
    # Verify admin token
    verify_admin_token(credentials)
    
    try:
        # Get total caller-IDs
        total_result = await db.execute(
            select(func.count()).select_from(CallerID)
        )
        total_caller_ids = total_result.scalar()
        
        # Get active caller-IDs
        active_result = await db.execute(
            select(func.count()).select_from(CallerID).where(CallerID.is_active == 1)
        )
        active_caller_ids = active_result.scalar()
        
        # Get recent caller-IDs (last 20)
        recent_result = await db.execute(
            select(CallerID).order_by(CallerID.created_at.desc()).limit(20)
        )
        recent_caller_ids = recent_result.scalars().all()
        
        # Get active reservations
        active_reservations_result = await db.execute(
            select(Reservation)
            .where(Reservation.reserved_until > datetime.utcnow())
            .order_by(Reservation.reserved_at.desc())
            .limit(50)
        )
        active_reservations = active_reservations_result.scalars().all()
        
        # Get recent API logs
        logs_result = await db.execute(
            select(APILog).order_by(APILog.timestamp.desc()).limit(100)
        )
        recent_logs = logs_result.scalars().all()
        
        # Get campaign stats (last 24 hours)
        campaign_stats_result = await db.execute(
            select(
                APILog.campaign,
                func.count().label('total_requests'),
                func.count(APILog.caller_id_allocated).label('successful_allocations')
            )
            .where(APILog.timestamp > datetime.utcnow() - timedelta(hours=24))
            .group_by(APILog.campaign)
            .order_by(func.count().desc())
            .limit(10)
        )
        campaign_stats = campaign_stats_result.all()
        
        # Get Redis stats
        redis_health = await redis_client.health_check()
        
        return templates.TemplateResponse(
            "dashboard.html",
            {
                "request": request,
                "total_caller_ids": total_caller_ids,
                "active_caller_ids": active_caller_ids,
                "recent_caller_ids": recent_caller_ids,
                "active_reservations": active_reservations,
                "recent_logs": recent_logs,
                "campaign_stats": campaign_stats,
                "redis_health": redis_health,
                "current_time": datetime.utcnow()
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error loading dashboard: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error loading dashboard"
        )


@app.get("/api/stats")
async def get_stats(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """
    Get API statistics in JSON format
    Requires admin token
    """
    # Verify admin token
    verify_admin_token(credentials)
    
    try:
        # Get total caller-IDs
        total_result = await db.execute(
            select(func.count()).select_from(CallerID)
        )
        total_caller_ids = total_result.scalar()
        
        # Get active caller-IDs
        active_result = await db.execute(
            select(func.count()).select_from(CallerID).where(CallerID.is_active == 1)
        )
        active_caller_ids = active_result.scalar()
        
        # Get active reservations count
        active_reservations_result = await db.execute(
            select(func.count()).select_from(Reservation)
            .where(Reservation.reserved_until > datetime.utcnow())
        )
        active_reservations = active_reservations_result.scalar()
        
        # Get requests in last hour
        requests_last_hour_result = await db.execute(
            select(func.count()).select_from(APILog)
            .where(APILog.timestamp > datetime.utcnow() - timedelta(hours=1))
        )
        requests_last_hour = requests_last_hour_result.scalar()
        
        # Get average response time
        avg_response_time_result = await db.execute(
            select(func.avg(APILog.response_time_ms)).select_from(APILog)
            .where(APILog.timestamp > datetime.utcnow() - timedelta(hours=1))
        )
        avg_response_time = avg_response_time_result.scalar() or 0
        
        return {
            "total_caller_ids": total_caller_ids,
            "active_caller_ids": active_caller_ids,
            "active_reservations": active_reservations,
            "requests_last_hour": requests_last_hour,
            "avg_response_time_ms": round(avg_response_time, 2),
            "timestamp": datetime.utcnow().isoformat()
        }
    
    except Exception as e:
        logger.error(f"Error getting stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving statistics"
        )


@app.delete("/api/reservation/{caller_id}")
async def release_reservation(
    caller_id: str,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
):
    """
    Manually release a caller-ID reservation
    Requires admin token
    """
    # Verify admin token
    verify_admin_token(credentials)
    
    try:
        # Release from Redis
        released = await redis_client.release_reservation(caller_id)
        
        # Delete from database
        await db.execute(
            delete(Reservation).where(Reservation.caller_id == caller_id)
        )
        await db.commit()
        
        return {
            "success": True,
            "message": f"Reservation released for {caller_id}",
            "released_from_redis": released
        }
    
    except Exception as e:
        logger.error(f"Error releasing reservation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error releasing reservation"
        )


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": settings.API_TITLE,
        "version": settings.API_VERSION,
        "status": "running",
        "endpoints": {
            "health": "/health",
            "next_cid": "/next-cid?to=<number>&campaign=<name>&agent=<name>",
            "add_number": "/add-number (POST, requires auth)",
            "dashboard": "/dashboard (requires auth)",
            "stats": "/api/stats (requires auth)"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG,
        workers=4 if not settings.DEBUG else 1
    )
