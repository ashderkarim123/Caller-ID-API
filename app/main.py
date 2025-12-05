from __future__ import annotations

import logging
from typing import Annotated

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jwt import InvalidTokenError
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from .config import Settings, get_settings
from .db import AsyncSessionMaker, get_db_session, init_db
from .redis_client import get_redis, redis_dependency
from .schemas import AddCallerIDRequest, CallerIDResponse, HealthResponse, NextCallerIDResponse
from .services.caller_id_service import CallerIDService
from .utils import enforce_ip_whitelist, utc_now

settings = get_settings()
logger = logging.getLogger("callerid")
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins or ["http://localhost", "https://dialer1.rjimmigrad.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
templates = Jinja2Templates(directory="app/templates")
app.mount("/static", StaticFiles(directory="app/static"), name="static")


async def admin_guard(
    request: Request,
    settings: Settings = Depends(get_settings),
) -> None:
    """Authorize dashboard and management endpoints."""

    enforce_ip_whitelist(request, settings)
    token = request.headers.get("x-admin-token") or request.headers.get("X-Admin-Token")
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        token = auth_header.split(" ", 1)[1]
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing admin token")
    if token == settings.admin_token:
        return
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
    except InvalidTokenError as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    if payload.get("role") != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin role required")


@app.on_event("startup")
async def on_startup() -> None:
    await init_db()
    redis = await get_redis()
    async with AsyncSessionMaker() as session:
        service = CallerIDService(session, redis, settings)
        await service.preload_lru_cache()
    logger.info("Caller ID API ready")


@app.get("/health", response_model=HealthResponse)
async def healthcheck(
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis=Depends(redis_dependency),
) -> HealthResponse:
    db_status = "ok"
    redis_status = "ok"
    try:
        await session.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Database healthcheck failed")
        db_status = f"error: {exc}"
    try:
        await redis.ping()
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception("Redis healthcheck failed")
        redis_status = f"error: {exc}"
    return HealthResponse(status="ok", db=db_status, redis=redis_status, timestamp=utc_now())


@app.get("/next-cid", response_model=NextCallerIDResponse)
async def next_caller_id(
    to: str,
    campaign: str,
    agent: str,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis=Depends(redis_dependency),
) -> NextCallerIDResponse:
    if not agent or not campaign:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="agent and campaign are required")
    service = CallerIDService(session, redis, settings)
    payload = await service.get_next_caller_id(destination=to, campaign=campaign, agent=agent)
    return NextCallerIDResponse(**payload)


@app.post("/add-number", response_model=CallerIDResponse, dependencies=[Depends(admin_guard)])
async def add_number(
    caller: AddCallerIDRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis=Depends(redis_dependency),
) -> CallerIDResponse:
    service = CallerIDService(session, redis, settings)
    new_caller = await service.add_caller_id(caller)
    return CallerIDResponse(
        caller_id=new_caller.caller_id,
        carrier=new_caller.carrier,
        area_code=new_caller.area_code,
        daily_limit=new_caller.daily_limit,
        hourly_limit=new_caller.hourly_limit,
        last_used=new_caller.last_used,
        meta=new_caller.meta,
    )


@app.get("/dashboard", response_class=HTMLResponse, dependencies=[Depends(admin_guard)])
async def dashboard(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_db_session)],
    redis=Depends(redis_dependency),
):
    service = CallerIDService(session, redis, settings)
    snapshot = await service.dashboard_snapshot()
    return templates.TemplateResponse(
        "dashboard.html",
        {
            "request": request,
            "app_name": settings.app_name,
            "now": utc_now(),
            **snapshot,
        },
    )
