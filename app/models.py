from __future__ import annotations

from datetime import datetime

from sqlalchemy import Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class CallerID(Base):
    __tablename__ = "caller_ids"

    caller_id: Mapped[str] = mapped_column(String(32), primary_key=True, unique=True, index=True)
    carrier: Mapped[str | None] = mapped_column(String(64), nullable=True)
    area_code: Mapped[str | None] = mapped_column(String(8), index=True)
    daily_limit: Mapped[int] = mapped_column(Integer, default=500)
    hourly_limit: Mapped[int] = mapped_column(Integer, default=50)
    last_used: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), nullable=True, index=True
    )
    meta: Mapped[dict | None] = mapped_column(JSONB, default=dict, nullable=True)


class Reservation(Base):
    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    caller_id: Mapped[str] = mapped_column(String(32), index=True)
    reserved_until: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), index=True)
    agent: Mapped[str] = mapped_column(String(64), index=True)
    campaign: Mapped[str] = mapped_column(String(64), index=True)
