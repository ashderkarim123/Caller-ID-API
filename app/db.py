from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import get_settings


settings = get_settings()


def _build_engine() -> AsyncEngine:
    return create_async_engine(
        settings.database_url,
        echo=settings.environment.lower() == "development",
        pool_pre_ping=True,
    )


def _build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    """Declarative base class for ORM models."""


engine = _build_engine()
AsyncSessionMaker = _build_sessionmaker(engine)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency that yields an async database session."""

    async with AsyncSessionMaker() as session:
        yield session


async def init_db() -> None:
    """Create database tables if they do not exist."""

    async with engine.begin() as conn:
        from . import models  # Local import to ensure models are registered

        await conn.run_sync(models.Base.metadata.create_all)
