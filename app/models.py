"""
Database models for Caller-ID Rotation API
"""
from sqlalchemy import Column, String, Integer, DateTime, JSON, BigInteger, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func
from datetime import datetime
from typing import Optional, Dict, Any

Base = declarative_base()


class CallerID(Base):
    """Caller ID model storing available phone numbers"""
    __tablename__ = "caller_ids"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    caller_id = Column(String(20), unique=True, nullable=False, index=True)
    carrier = Column(String(100), nullable=True)
    area_code = Column(String(10), nullable=True, index=True)
    daily_limit = Column(Integer, default=500, nullable=False)
    hourly_limit = Column(Integer, default=100, nullable=False)
    last_used = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    meta = Column(JSON, nullable=True)  # Extra metadata in JSONB format
    is_active = Column(Integer, default=1, nullable=False)  # 1=active, 0=disabled
    
    # Composite indexes for performance
    __table_args__ = (
        Index('idx_area_code_active', 'area_code', 'is_active'),
        Index('idx_last_used', 'last_used'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'caller_id': self.caller_id,
            'carrier': self.carrier,
            'area_code': self.area_code,
            'daily_limit': self.daily_limit,
            'hourly_limit': self.hourly_limit,
            'last_used': self.last_used.isoformat() if self.last_used else None,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'meta': self.meta,
            'is_active': self.is_active
        }


class Reservation(Base):
    """Reservation model tracking active caller-ID allocations"""
    __tablename__ = "reservations"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    caller_id = Column(String(20), nullable=False, index=True)
    reserved_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    reserved_until = Column(DateTime(timezone=True), nullable=False, index=True)
    agent = Column(String(100), nullable=True, index=True)
    campaign = Column(String(100), nullable=True, index=True)
    destination = Column(String(20), nullable=True)  # The number being called
    meta = Column(JSON, nullable=True)  # Extra metadata
    
    # Composite indexes for performance
    __table_args__ = (
        Index('idx_caller_id_reserved_until', 'caller_id', 'reserved_until'),
        Index('idx_agent_campaign', 'agent', 'campaign'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'caller_id': self.caller_id,
            'reserved_at': self.reserved_at.isoformat() if self.reserved_at else None,
            'reserved_until': self.reserved_until.isoformat() if self.reserved_until else None,
            'agent': self.agent,
            'campaign': self.campaign,
            'destination': self.destination,
            'meta': self.meta
        }


class APILog(Base):
    """API request logging for monitoring and analytics"""
    __tablename__ = "api_logs"
    
    id = Column(BigInteger, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False, index=True)
    endpoint = Column(String(200), nullable=False)
    method = Column(String(10), nullable=False)
    agent = Column(String(100), nullable=True, index=True)
    campaign = Column(String(100), nullable=True, index=True)
    caller_id_allocated = Column(String(20), nullable=True)
    destination = Column(String(20), nullable=True)
    response_time_ms = Column(Integer, nullable=True)
    status_code = Column(Integer, nullable=True)
    error_message = Column(String(500), nullable=True)
    meta = Column(JSON, nullable=True)
    
    # Composite indexes for analytics
    __table_args__ = (
        Index('idx_timestamp_campaign', 'timestamp', 'campaign'),
        Index('idx_timestamp_agent', 'timestamp', 'agent'),
    )
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert model to dictionary"""
        return {
            'id': self.id,
            'timestamp': self.timestamp.isoformat() if self.timestamp else None,
            'endpoint': self.endpoint,
            'method': self.method,
            'agent': self.agent,
            'campaign': self.campaign,
            'caller_id_allocated': self.caller_id_allocated,
            'destination': self.destination,
            'response_time_ms': self.response_time_ms,
            'status_code': self.status_code,
            'error_message': self.error_message,
            'meta': self.meta
        }
