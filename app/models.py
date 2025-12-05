"""
Database models for Caller-ID Rotation API
"""
from sqlalchemy import Column, String, Integer, DateTime, JSON, Index
from sqlalchemy.sql import func
from app.db import Base


class CallerID(Base):
    """Caller-ID model"""
    __tablename__ = "caller_ids"
    
    caller_id = Column(String(20), primary_key=True, index=True)
    carrier = Column(String(100), nullable=True)
    area_code = Column(String(3), nullable=True, index=True)
    daily_limit = Column(Integer, default=1000)
    hourly_limit = Column(Integer, default=100)
    daily_used = Column(Integer, default=0)
    hourly_used = Column(Integer, default=0)
    last_used = Column(DateTime(timezone=True), nullable=True, index=True)
    total_uses = Column(Integer, default=0)
    is_active = Column(Integer, default=1)  # 1 = active, 0 = inactive
    meta = Column(JSON, nullable=True)  # Additional metadata
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_caller_id_area_code', 'area_code', 'is_active'),
        Index('idx_caller_id_last_used', 'last_used'),
    )


class Reservation(Base):
    """Reservation model for tracking active reservations"""
    __tablename__ = "reservations"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    caller_id = Column(String(20), nullable=False, index=True)
    agent = Column(String(100), nullable=False, index=True)
    campaign = Column(String(100), nullable=False, index=True)
    reserved_at = Column(DateTime(timezone=True), server_default=func.now())
    reserved_until = Column(DateTime(timezone=True), nullable=False, index=True)
    to_number = Column(String(20), nullable=True)
    
    # Indexes for performance
    __table_args__ = (
        Index('idx_reservation_caller_agent', 'caller_id', 'agent'),
        Index('idx_reservation_until', 'reserved_until'),
    )


class APIRequest(Base):
    """Logging model for API requests"""
    __tablename__ = "api_requests"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    endpoint = Column(String(200), nullable=False, index=True)
    method = Column(String(10), nullable=False)
    agent = Column(String(100), nullable=True, index=True)
    campaign = Column(String(100), nullable=True, index=True)
    caller_id = Column(String(20), nullable=True, index=True)
    ip_address = Column(String(45), nullable=True)
    status_code = Column(Integer, nullable=False)
    response_time_ms = Column(Integer, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    __table_args__ = (
        Index('idx_api_requests_created', 'created_at'),
        Index('idx_api_requests_agent_campaign', 'agent', 'campaign'),
    )
