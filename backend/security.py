import re
import logging
import unicodedata
import html
from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt, JWTError, ExpiredSignatureError
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer

from .config import (
    DEMO_PASSWORD,
    DEMO_USERNAME,
    JWT_ALGORITHM,
    JWT_EXPIRE_MINUTES,
    JWT_SECRET_KEY,
    MAX_TEXT_LENGTH,
    REQUIRE_AUTH,
)

oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)
logger = logging.getLogger("voice_os_bharat.auth")


def _auth_error(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail={"error": "AUTH_ERROR", "message": message, "details": None},
    )


def validate_security_configuration() -> None:
    if REQUIRE_AUTH and not JWT_SECRET_KEY:
        raise RuntimeError("JWT_SECRET_KEY is required when REQUIRE_AUTH=true")


def verify_demo_user(username: str, password: str) -> bool:
    return username == DEMO_USERNAME and password == DEMO_PASSWORD


def create_access_token(subject: str) -> str:
    if not JWT_SECRET_KEY:
        raise RuntimeError("JWT_SECRET_KEY is not configured")
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": expire,
    }
    return jwt.encode(payload, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    if not JWT_SECRET_KEY:
        logger.error("auth_token_validation_failed reason=missing_secret")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "CONFIG_ERROR", "message": "Authentication is not configured", "details": None},
        )
    try:
        return jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except ExpiredSignatureError as exc:
        logger.warning("auth_token_validation_failed reason=expired")
        raise _auth_error("Token has expired") from exc
    except JWTError as exc:
        logger.error("auth_token_validation_failed reason=jwt_error")
        raise _auth_error("Token validation failed") from exc


def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme_optional),
) -> Optional[str]:
    if token and not JWT_SECRET_KEY and not REQUIRE_AUTH:
        logger.warning("auth_token_ignored_missing_secret request_id=%s", getattr(request.state, "request_id", "n/a"))
        return None
    if not token:
        if REQUIRE_AUTH:
            logger.warning("auth_missing_token request_id=%s", getattr(request.state, "request_id", "n/a"))
            raise _auth_error("Missing bearer token")
        return None

    payload = decode_access_token(token)
    subject = str(payload.get("sub", "")).strip()
    if not subject:
        logger.warning("auth_token_validation_failed reason=missing_subject request_id=%s", getattr(request.state, "request_id", "n/a"))
        raise _auth_error("Invalid token subject")
    logger.info("auth_token_validation_success user=%s request_id=%s", subject, getattr(request.state, "request_id", "n/a"))
    return subject


def get_optional_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme_optional),
) -> Optional[str]:
    return get_current_user(request=request, token=token)


def sanitize_text(text: str) -> str:
    clean_text = unicodedata.normalize("NFKC", str(text or "")).strip()
    clean_text = html.escape(clean_text)
    clean_text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", clean_text)
    clean_text = re.sub(r"\s+", " ", clean_text).strip()
    return clean_text[:MAX_TEXT_LENGTH]
