import os
import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "change-this-in-production")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

DEMO_USERNAME = os.getenv("DEMO_AUTH_USERNAME", "demo")
DEMO_PASSWORD = os.getenv("DEMO_AUTH_PASSWORD", "demo123")

MAX_TEXT_LENGTH = int(os.getenv("MAX_TEXT_LENGTH", "1000"))

oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)
logger = logging.getLogger("voice_os_bharat.auth")


def verify_demo_user(username: str, password: str) -> bool:
    return username == DEMO_USERNAME and password == DEMO_PASSWORD


def create_access_token(subject: str) -> str:
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError as exc:
        logger.warning("auth_token_validation_failed reason=expired")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired") from exc
    except jwt.InvalidTokenError as exc:
        logger.warning("auth_token_validation_failed reason=invalid")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token") from exc
    except jwt.PyJWTError as exc:
        logger.error("auth_token_validation_failed reason=jwt_error")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token validation failed") from exc


def get_optional_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme_optional),
) -> Optional[str]:
    # Demo-safe mode: no token means allow request without auth.
    if not token:
        logger.info("auth_bypass mode=demo request_id=%s", getattr(request.state, "request_id", "n/a"))
        return None

    payload = decode_access_token(token)
    subject = str(payload.get("sub", "")).strip()
    if not subject:
        logger.warning("auth_token_validation_failed reason=missing_subject request_id=%s", getattr(request.state, "request_id", "n/a"))
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject")
    logger.info("auth_token_validation_success user=%s request_id=%s", subject, getattr(request.state, "request_id", "n/a"))
    return subject


def sanitize_text(text: str) -> str:
    clean_text = (text or "").strip()
    # Remove non-printable control characters while preserving multilingual text.
    clean_text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", clean_text)
    return clean_text
