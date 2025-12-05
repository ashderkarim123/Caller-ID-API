"""
Authentication and authorization utilities
"""
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.config import settings
import logging

logger = logging.getLogger(__name__)

security = HTTPBearer()


def verify_admin_token(credentials: HTTPAuthorizationCredentials = Security(security)) -> bool:
    """
    Verify admin token from Authorization header
    """
    token = credentials.credentials
    
    if token != settings.ADMIN_TOKEN:
        logger.warning(f"Invalid admin token attempt")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid admin token"
        )
    
    return True


def get_client_ip(request) -> str:
    """Extract client IP from request"""
    # Check for forwarded headers (from reverse proxy)
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip
    
    if request.client:
        return request.client.host
    
    return "unknown"
