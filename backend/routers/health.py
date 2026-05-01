import logging
from typing import Optional
from fastapi import APIRouter, Depends, Request, status, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..security import get_current_user
from ..config import APP_ENV
from ..api_utils import format_response

logger = logging.getLogger("voice_os_bharat.routers.health")
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

@router.get("/health")
def health_check() -> dict:
    """Basic system health check."""
    return {
        "status": "ok",
        "model_loaded": True,
        "version": "1.0"
    }
