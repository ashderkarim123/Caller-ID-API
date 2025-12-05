"""SQLAlchemy ORM models."""

from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class CallerID(Base):
    """Caller ID metadata and limits."""

    __tablename__ = "caller_ids"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    caller_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    carrier: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    area_code: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, index=True)
    daily_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    hourly_limit: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    last_used: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    reservations: Mapped[list["Reservation"]] = relationship(back_populates="caller")


class Reservation(Base):
    """Reservation log for auditing allocations."""

    __tablename__ = "reservations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    caller_id: Mapped[str] = mapped_column(
        String(32), ForeignKey("caller_ids.caller_id", ondelete="CASCADE"), index=True
    )
    reserved_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    agent: Mapped[str] = mapped_column(String(64), nullable=False)
    campaign: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=datetime.utcnow
    )

    caller: Mapped["CallerID"] = relationship(back_populates="reservations")
