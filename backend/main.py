import logging
import os
import uuid
from time import perf_counter
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from slowapi import Limiter

from .api_utils import format_response, raise_api_error
from .config import APP_ENV
from .logging_config import configure_logging
from .security import create_access_token, verify_demo_user
# Routers
from .routers import health, audio
from .routers.auth_router import router as auth_router
from .routers.conversations_router import router as conversations_router
from .db.mongo import init_indexes

app = FastAPI(title="Voice OS Bharat")
configure_logging(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("voice_os_bharat")

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.middleware("http")
async def add_request_id_and_timing(request: Request, call_next):
    started = perf_counter()
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    request.state.request_id = request_id
    
    response = await call_next(request)
    
    elapsed_ms = (perf_counter() - started) * 1000.0
    logger.info(
        "request_completed",
        extra={
            "event": "request",
            "method": request.method,
            "endpoint": request.url.path,
            "status_code": response.status_code,
            "total_time_ms": round(elapsed_ms, 2),
        },
    )
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{elapsed_ms:.2f}ms"
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "Unhandled exception on path %s request_id=%s",
        request.url.path,
        getattr(request.state, "request_id", "n/a"),
    )
    return JSONResponse(status_code=500, content=format_response(False, None, "Something went wrong"))


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    _ = request
    detail = exc.detail
    # If it's already properly formatted via raise_api_error
    if isinstance(detail, dict) and {"success", "data", "error"}.issubset(set(detail.keys())):
        payload = detail
    elif isinstance(detail, dict) and "error" in detail:
        payload = format_response(False, None, detail.get("message") or detail.get("error") or "Request failed")
    elif isinstance(detail, str):
        payload = format_response(False, None, detail)
    else:
        payload = format_response(False, None, "Request failed")
    return JSONResponse(status_code=exc.status_code, content=payload)


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "https://voice-os-bhaarat.vercel.app"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def custom_rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    logger.warning("rate_limit_exceeded path=%s ip=%s", request.url.path, get_remote_address(request))
    return JSONResponse(
        status_code=429,
        content=format_response(False, None, "Too many requests, please try again later")
    )

app.add_exception_handler(RateLimitExceeded, custom_rate_limit_exceeded_handler)


@app.on_event("startup")
def startup() -> None:
    logger.info("application_startup event=startup version=1.1.0 env=%s", APP_ENV)
    
    import shutil
    if not shutil.which("ffmpeg"):
        logger.warning("WARNING: ffmpeg not found. STT may fail.")
        print("WARNING: ffmpeg not found. STT may fail.")

    init_indexes()

@app.on_event("shutdown")
def shutdown() -> None:
    logger.info("application_shutdown event=shutdown")


@app.post("/api/auth/token")
@limiter.limit("10/minute")
def issue_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends()) -> dict:
    try:
        if not verify_demo_user(form_data.username, form_data.password):
            logger.warning(
                "auth_login_failed user=%s request_id=%s",
                form_data.username,
                getattr(request.state, "request_id", "n/a"),
            )
            raise_api_error(status.HTTP_401_UNAUTHORIZED, "AUTH_ERROR", "Invalid credentials")

        access_token = create_access_token(subject=form_data.username)
        logger.info(
            "auth_login_success user=%s request_id=%s",
            form_data.username,
            getattr(request.state, "request_id", "n/a"),
        )
        return format_response(True, {
            "access_token": access_token,
            "token_type": "bearer",
        })
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("token_issue_failed request_id=%s", getattr(request.state, "request_id", "n/a"))
        raise_api_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "AUTH_ERROR", "Failed to issue access token")

# Include routers
app.include_router(health.router)
app.include_router(audio.router)
app.include_router(auth_router)
app.include_router(conversations_router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000)
