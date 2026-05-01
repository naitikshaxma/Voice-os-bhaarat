"""Authentication routes: signup + login."""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from passlib.context import CryptContext
from pymongo.errors import DuplicateKeyError

from ..db.mongo import users_collection, serialize_doc
from ..security import create_access_token
from ..api_utils import format_response
from ..config import JWT_SECRET_KEY

logger = logging.getLogger("voice_os_bharat.auth_router")
router = APIRouter(prefix="/api/auth", tags=["auth"])

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


# =========================
# REQUEST MODELS
# =========================
class SignupRequest(BaseModel):
    name: str
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


# =========================
# HELPERS
# =========================
def _hash_password(password: str) -> str:
    return pwd_context.hash(password)


def _verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


# =========================
# SIGNUP
# =========================
@router.post("/signup")
def signup(body: SignupRequest):
    try:
        if len(body.password) < 6:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=format_response(False, None, "Password must be at least 6 characters"),
            )

        email_lower = body.email.lower().strip()

        user_doc = {
            "name": body.name.strip(),
            "email": email_lower,
            "hashed_password": _hash_password(body.password),
        }

        result = users_collection.insert_one(user_doc)
        user_id = str(result.inserted_id)

        logger.info("signup_success user_id=%s", user_id)

        token: Optional[str] = None
        if JWT_SECRET_KEY:
            token = create_access_token(subject=user_id)

        return format_response(True, {
            "user_id": user_id,
            "name": body.name.strip(),
            "email": email_lower,
            "access_token": token,
            "token_type": "bearer",
        })

    except DuplicateKeyError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=format_response(False, None, "Email already registered"),
        )

    except Exception as e:
        logger.exception("signup_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=format_response(False, None, "Signup failed"),
        )


# =========================
# LOGIN
# =========================
@router.post("/login")
def login(body: LoginRequest):
    try:
        email_lower = body.email.lower().strip()

        user = users_collection.find_one({"email": email_lower})

        # 🔥 FIX: safe checks (prevents 500 crash)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=format_response(False, None, "User not found"),
            )

        if not user.get("hashed_password"):
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=format_response(False, None, "User data corrupted"),
            )

        if not _verify_password(body.password, user["hashed_password"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=format_response(False, None, "Invalid password"),
            )

        if not JWT_SECRET_KEY:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=format_response(False, None, "JWT not configured"),
            )

        user = serialize_doc(user)
        user_id = user["_id"]

        token = create_access_token(subject=user_id)

        logger.info("login_success user_id=%s", user_id)

        return format_response(True, {
            "user_id": user_id,
            "name": user.get("name", ""),
            "email": email_lower,
            "access_token": token,
            "token_type": "bearer",
        })

    except HTTPException:
        raise

    except Exception:
        logger.exception("login_error")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=format_response(False, None, "Login failed"),
        )