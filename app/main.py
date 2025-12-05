"""
Main FastAPI application for Caller-ID Rotation API
"""
import time
import logging
from typing import Optional
from datetime import datetime
from fastapi import FastAPI, Depends, HTTPException, Request, Query, status
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, desc
from pydantic import BaseModel, Field

from app.config import settings
from app.db import get_db, init_db, AsyncSessionLocal
from app.models import CallerID, Reservation, APIRequest
from app.redis_client import redis_client
from app.utils import get_next_caller_id, validate_caller_id_limits
from app.auth import verify_admin_token, get_client_ip

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title=settings.API_TITLE,
    version=settings.API_VERSION,
    docs_url=None,  # Disable docs in production
    redoc_url=None
)

# Templates
templates = Jinja2Templates(directory="app/templates")

# CORS middleware (restrict in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Request/Response models
class AddNumberRequest(BaseModel):
    caller_id: str = Field(..., description="Caller-ID phone number")
    carrier: Optional[str] = Field(None, description="Carrier name")
    area_code: Optional[str] = Field(None, description="Area code")
    daily_limit: Optional[int] = Field(1000, description="Daily usage limit")
    hourly_limit: Optional[int] = Field(100, description="Hourly usage limit")
    meta: Optional[dict] = Field(None, description="Additional metadata")


class NextCIDResponse(BaseModel):
    caller_id: str
    carrier: Optional[str] = None
    area_code: Optional[str] = None
    meta: dict = {}


# Middleware for request logging
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all API requests"""
    start_time = time.time()
    
    # Process request
    response = await call_next(request)
    
    # Calculate response time
    process_time = int((time.time() - start_time) * 1000)
    
    # Log to database (async, don't block - fire and forget)
    # Use background task to avoid blocking response
    try:
        async with AsyncSessionLocal() as db:
            log_entry = APIRequest(
                endpoint=str(request.url.path),
                method=request.method,
                ip_address=get_client_ip(request),
                status_code=response.status_code,
                response_time_ms=process_time
            )
            db.add(log_entry)
            await db.commit()
    except Exception as e:
        logger.error(f"Failed to log request: {e}")
    
    return response


# Startup event
@app.on_event("startup")
async def startup_event():
    """Initialize database and Redis on startup"""
    logger.info("Starting Caller-ID Rotation API...")
    
    # Initialize database
    await init_db()
    logger.info("Database initialized")
    
    # Connect to Redis
    await redis_client.connect()
    logger.info("Redis connected")
    
    logger.info(f"API ready at http://{settings.API_HOST}:{settings.API_PORT}")


# Shutdown event
@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown"""
    logger.info("Shutting down...")
    await redis_client.disconnect()
    logger.info("Redis disconnected")


# Health check endpoint
@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Check Redis connection
        await redis_client.connect()
        redis_status = "ok"
    except Exception as e:
        redis_status = f"error: {str(e)}"
    
    return {
        "status": "healthy",
        "redis": redis_status,
        "timestamp": datetime.utcnow().isoformat()
    }


# Get next caller-ID endpoint
@app.get("/next-cid", response_model=NextCIDResponse)
async def get_next_cid(
    to: str = Query(..., description="Destination phone number"),
    campaign: str = Query(..., description="Campaign name"),
    agent: str = Query(..., description="Agent name/ID"),
    request: Request = None,
    db: AsyncSession = Depends(get_db)
):
    """
    Get the next available caller-ID for a call
    
    This is the main endpoint used by VICIdial/Asterisk dialplan.
    Returns a JSON response with the caller-ID to use.
    """
    start_time = time.time()
    
    try:
        
        # Get next caller-ID
        result = await get_next_caller_id(
            db=db,
            to_number=to,
            campaign=campaign,
            agent=agent
        )
        
        if not result:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No available caller-ID found"
            )
        
        # Log the request
        try:
            log_entry = APIRequest(
                endpoint="/next-cid",
                method="GET",
                agent=agent,
                campaign=campaign,
                caller_id=result["caller_id"],
                ip_address=get_client_ip(request) if request else None,
                status_code=200,
                response_time_ms=int((time.time() - start_time) * 1000)
            )
            db.add(log_entry)
            await db.commit()
        except Exception as e:
            logger.error(f"Failed to log request: {e}")
        
        return NextCIDResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in /next-cid: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Internal server error: {str(e)}"
        )


# Add caller-ID endpoint
@app.post("/add-number")
async def add_number(
    request_data: AddNumberRequest,
    admin_token: str = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Add a new caller-ID to the system
    
    Requires admin token authentication.
    """
    try:
        # Check if caller-ID already exists
        existing = await db.execute(
            select(CallerID).where(CallerID.caller_id == request_data.caller_id)
        )
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Caller-ID {request_data.caller_id} already exists"
            )
        
        # Extract area code if not provided
        area_code = request_data.area_code
        if not area_code and request_data.caller_id:
            digits = ''.join(filter(str.isdigit, request_data.caller_id))
            if len(digits) >= 3:
                area_code = digits[:3]
        
        # Create new caller-ID
        caller_id = CallerID(
            caller_id=request_data.caller_id,
            carrier=request_data.carrier,
            area_code=area_code,
            daily_limit=request_data.daily_limit or settings.DEFAULT_DAILY_LIMIT,
            hourly_limit=request_data.hourly_limit or settings.DEFAULT_HOURLY_LIMIT,
            meta=request_data.meta
        )
        
        db.add(caller_id)
        await db.commit()
        await db.refresh(caller_id)
        
        logger.info(f"Added new caller-ID: {request_data.caller_id}")
        
        return {
            "status": "success",
            "message": f"Caller-ID {request_data.caller_id} added successfully",
            "caller_id": caller_id.caller_id
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error adding caller-ID: {e}", exc_info=True)
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to add caller-ID: {str(e)}"
        )


# Dashboard endpoint
@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    admin_token: str = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db)
):
    """
    Admin dashboard showing caller-ID statistics
    
    Requires admin token authentication.
    """
    try:
        # Get all caller-IDs
        caller_ids_result = await db.execute(
            select(CallerID).order_by(desc(CallerID.last_used))
        )
        caller_ids = caller_ids_result.scalars().all()
        
        # Get statistics
        total_caller_ids = len(caller_ids)
        active_caller_ids = sum(1 for cid in caller_ids if cid.is_active == 1)
        
        # Get usage stats from Redis
        caller_id_stats = []
        for cid_obj in caller_ids:
            daily_used = await redis_client.get_usage_count(cid_obj.caller_id, "daily")
            hourly_used = await redis_client.get_usage_count(cid_obj.caller_id, "hourly")
            
            reservation_info = await redis_client.get_reservation_info(cid_obj.caller_id)
            is_reserved = reservation_info is not None
            
            caller_id_stats.append({
                "caller_id": cid_obj.caller_id,
                "carrier": cid_obj.carrier,
                "area_code": cid_obj.area_code,
                "daily_limit": cid_obj.daily_limit,
                "hourly_limit": cid_obj.hourly_limit,
                "daily_used": daily_used,
                "hourly_used": hourly_used,
                "last_used": cid_obj.last_used.isoformat() if cid_obj.last_used else None,
                "total_uses": cid_obj.total_uses,
                "is_active": cid_obj.is_active == 1,
                "is_reserved": is_reserved,
                "reservation": reservation_info
            })
        
        # Get active reservations
        active_reservations = await redis_client.get_all_reservations()
        
        # Get recent API requests
        recent_requests_result = await db.execute(
            select(APIRequest)
            .order_by(desc(APIRequest.created_at))
            .limit(100)
        )
        recent_requests = recent_requests_result.scalars().all()
        
        # Campaign statistics
        campaign_stats_result = await db.execute(
            select(
                APIRequest.campaign,
                func.count(APIRequest.id).label("count"),
                func.max(APIRequest.created_at).label("last_used")
            )
            .where(APIRequest.campaign.isnot(None))
            .group_by(APIRequest.campaign)
            .order_by(desc("count"))
            .limit(20)
        )
        campaign_stats = campaign_stats_result.all()
        
        return templates.TemplateResponse("dashboard.html", {
            "request": request,
            "total_caller_ids": total_caller_ids,
            "active_caller_ids": active_caller_ids,
            "caller_id_stats": caller_id_stats,
            "active_reservations": active_reservations,
            "recent_requests": recent_requests,
            "campaign_stats": campaign_stats
        })
        
    except Exception as e:
        logger.error(f"Error loading dashboard: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to load dashboard: {str(e)}"
        )


# API stats endpoint (JSON)
@app.get("/api/stats")
async def api_stats(
    admin_token: str = Depends(verify_admin_token),
    db: AsyncSession = Depends(get_db)
):
    """Get API statistics in JSON format"""
    try:
        # Count caller-IDs
        total_result = await db.execute(select(func.count(CallerID.caller_id)))
        total_caller_ids = total_result.scalar()
        
        active_result = await db.execute(
            select(func.count(CallerID.caller_id)).where(CallerID.is_active == 1)
        )
        active_caller_ids = active_result.scalar()
        
        # Get active reservations
        active_reservations = await redis_client.get_all_reservations()
        
        return {
            "total_caller_ids": total_caller_ids,
            "active_caller_ids": active_caller_ids,
            "active_reservations": len(active_reservations),
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Error getting stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.API_HOST,
        port=settings.API_PORT,
        reload=settings.DEBUG
    )
