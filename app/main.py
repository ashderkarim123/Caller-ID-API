"""FastAPI entrypoint."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

from fastapi import Depends, FastAPI, Query, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from redis.asyncio import Redis
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .config import settings
from .db import Base, engine, get_session
from .models import CallerID, Reservation
from .redis_client import get_redis
from .schemas import CallerIDCreate, NextCIDResponse
from .services import ensure_lru, get_next_caller_id, upsert_caller_id
from .services.caller_id import LAST_REQUESTS_KEY
from .utils import enforce_admin, utcnow

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://dialer1.rjimmigrad.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
static_dir = BASE_DIR / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.on_event("startup")
async def startup_event() -> None:
    """Prepare database tables and warm caches."""

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine) as session:
        stmt = select(CallerID)
        result = await session.execute(stmt)
        caller_ids = result.scalars().all()

    redis = await get_redis()
    for caller in caller_ids:
        await ensure_lru(redis, caller.caller_id, caller.area_code)
    logger.info("Loaded %s caller IDs into Redis LRU", len(caller_ids))


@app.get("/health")
async def health(
    session: AsyncSession = Depends(get_session), redis: Redis = Depends(get_redis)
) -> Dict[str, Any]:
    caller_count = await session.scalar(select(func.count(CallerID.id)))
    redis_ok = await redis.ping()
    return {
        "status": "ok",
        "database": bool(caller_count or caller_count == 0),
        "redis": redis_ok,
        "time": utcnow().isoformat(),
    }


@app.get("/next-cid", response_model=NextCIDResponse)
async def next_caller_id(
    to: str = Query(..., alias="to"),
    campaign: str = Query(...),
    agent: str = Query(...),
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> NextCIDResponse:
    logger.info("next-cid requested by agent=%s campaign=%s", agent, campaign)
    return await get_next_caller_id(session, redis, destination=to, campaign=campaign, agent=agent)


@app.post("/add-number")
async def add_number(
    payload: CallerIDCreate,
    request: Request,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> JSONResponse:
    admin_token = request.headers.get("X-Admin-Token")
    client_ip = request.client.host if request.client else None
    enforce_admin(admin_token, client_ip)
    result = await upsert_caller_id(session, redis, payload)
    return JSONResponse(status_code=status.HTTP_201_CREATED, content=result.model_dump())


@app.get("/dashboard")
async def dashboard(
    request: Request,
    session: AsyncSession = Depends(get_session),
    redis: Redis = Depends(get_redis),
) -> Any:
    admin_token = request.headers.get("X-Admin-Token")
    client_ip = request.client.host if request.client else None
    enforce_admin(admin_token, client_ip)

    caller_stmt = select(CallerID).order_by(CallerID.area_code, CallerID.last_used)
    caller_result = await session.execute(caller_stmt)
    caller_ids = caller_result.scalars().all()

    reservation_stmt = (
        select(Reservation)
        .order_by(Reservation.created_at.desc())
        .limit(50)
    )
    reservation_result = await session.execute(reservation_stmt)
    reservations = reservation_result.scalars().all()

    active = [r for r in reservations if r.reserved_until > utcnow()]

    last_requests: List[Dict[str, Any]] = []
    raw_requests = await redis.lrange(LAST_REQUESTS_KEY, 0, 49)
    for entry in raw_requests:
        try:
            last_requests.append(json.loads(entry))
        except Exception:  # pragma: no cover - defensive
            continue

    per_campaign: Dict[str, int] = {}
    async for key in redis.scan_iter(match="cid:campaign:*"):
        campaign_name = key.split("cid:campaign:", 1)[-1]
        value = await redis.get(key)
        per_campaign[campaign_name] = int(value or 0)

    context = {
        "request": request,
        "stats": {
            "total_caller_ids": len(caller_ids),
            "active_reservations": len(active),
            "last_requests": last_requests,
            "per_campaign": per_campaign,
        },
        "caller_ids": caller_ids,
        "reservations": reservations,
        "app_name": settings.app_name,
    }
    return templates.TemplateResponse("dashboard.html", context)
