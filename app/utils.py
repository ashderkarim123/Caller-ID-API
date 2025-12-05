"""
Utility functions for the Caller-ID Rotation API
"""
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging
import jwt
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import re

from app.config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer()


def extract_area_code(phone_number: str) -> Optional[str]:
    """Extract area code from phone number"""
    # Remove non-numeric characters
    cleaned = re.sub(r'\D', '', phone_number)
    
    # Handle different formats
    if len(cleaned) == 10:
        return cleaned[:3]
    elif len(cleaned) == 11 and cleaned.startswith('1'):
        return cleaned[1:4]
    elif len(cleaned) >= 3:
        return cleaned[:3]
    
    return None


def validate_phone_number(phone_number: str) -> bool:
    """Validate phone number format"""
    cleaned = re.sub(r'\D', '', phone_number)
    return len(cleaned) >= 10


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """Create JWT access token"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    
    return encoded_jwt


def verify_token(token: str) -> Dict[str, Any]:
    """Verify and decode JWT token"""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )


def verify_admin_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> bool:
    """Verify admin token from Authorization header"""
    token = credentials.credentials
    
    # Check if it's the simple admin token
    if token == settings.ADMIN_TOKEN:
        return True
    
    # Try to verify as JWT token
    try:
        payload = verify_token(token)
        if payload.get("admin") == True:
            return True
    except HTTPException:
        pass
    
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Invalid admin token"
    )


def sanitize_input(value: str, max_length: int = 100) -> str:
    """Sanitize user input"""
    if not value:
        return ""
    
    # Remove potentially dangerous characters
    sanitized = re.sub(r'[^\w\s\-\.\@\+]', '', value)
    
    # Limit length
    return sanitized[:max_length]


async def log_api_request(
    db,
    endpoint: str,
    method: str,
    agent: Optional[str] = None,
    campaign: Optional[str] = None,
    caller_id_allocated: Optional[str] = None,
    destination: Optional[str] = None,
    response_time_ms: Optional[int] = None,
    status_code: Optional[int] = None,
    error_message: Optional[str] = None,
    meta: Optional[Dict] = None
):
    """Log API request to database"""
    from app.models import APILog
    from sqlalchemy import insert
    
    try:
        log_entry = APILog(
            endpoint=endpoint,
            method=method,
            agent=agent,
            campaign=campaign,
            caller_id_allocated=caller_id_allocated,
            destination=destination,
            response_time_ms=response_time_ms,
            status_code=status_code,
            error_message=error_message,
            meta=meta
        )
        
        db.add(log_entry)
        await db.commit()
    except Exception as e:
        logger.error(f"Error logging API request: {e}")
        # Don't raise exception, just log it


def format_phone_number(phone_number: str, format_type: str = "e164") -> str:
    """Format phone number to specified format"""
    cleaned = re.sub(r'\D', '', phone_number)
    
    if format_type == "e164":
        # E.164 format: +1XXXXXXXXXX
        if len(cleaned) == 10:
            return f"+1{cleaned}"
        elif len(cleaned) == 11 and cleaned.startswith('1'):
            return f"+{cleaned}"
        return f"+{cleaned}"
    
    elif format_type == "nanp":
        # North American format: (XXX) XXX-XXXX
        if len(cleaned) == 10:
            return f"({cleaned[:3]}) {cleaned[3:6]}-{cleaned[6:]}"
        elif len(cleaned) == 11 and cleaned.startswith('1'):
            return f"({cleaned[1:4]}) {cleaned[4:7]}-{cleaned[7:]}"
    
    return cleaned


class Timer:
    """Simple timer context manager for measuring execution time"""
    
    def __init__(self):
        self.start_time = None
        self.end_time = None
    
    def __enter__(self):
        self.start_time = datetime.utcnow()
        return self
    
    def __exit__(self, *args):
        self.end_time = datetime.utcnow()
    
    @property
    def elapsed_ms(self) -> int:
        """Get elapsed time in milliseconds"""
        if self.start_time and self.end_time:
            delta = self.end_time - self.start_time
            return int(delta.total_seconds() * 1000)
        return 0
