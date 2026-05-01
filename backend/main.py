import logging
import os
import uuid
from time import perf_counter

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.security import OAuth2PasswordRequestForm
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from slowapi import Limiter

from .api_utils import format_response, raise_api_error
from .config import APP_ENV
from .logging_config import configure_logging
from .security import create_access_token, verify_demo_user

from .routers import health, audio
from .routers.auth_router import router as auth_router
from .routers.conversations_router import router as conversations_router
from .db.mongo import init_indexes

app = FastAPI(title="Voice OS Bharat")

# Logging
configure_logging(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("voice_os_bharat")

# Rate limiter
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# =========================
# FINAL CORS FIX
# =========================
origins = [
    "http://localhost:5173",
    "https://voice-os-bhaarat.vercel.app",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex=r"https://.*\.vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# =========================


# Request logging middleware
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
            "method": request.method,
            "endpoint": request.url.path,
            "status_code": response.status_code,
            "total_time_ms": round(elapsed_ms, 2),
        },
    )
    response.headers["X-Request-ID"] = request_id
    response.headers["X-Response-Time"] = f"{elapsed_ms:.2f}ms"
    return response


# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception: %s", request.url.path)
    return JSONResponse(
        status_code=500,
        content=format_response(False, None, "Something went wrong"),
    )


# HTTP exception handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    detail = exc.detail

    if isinstance(detail, dict) and {"success", "data", "error"}.issubset(detail.keys()):
        payload = detail
    elif isinstance(detail, str):
        payload = format_response(False, None, detail)
    else:
        payload = format_response(False, None, "Request failed")

    return JSONResponse(status_code=exc.status_code, content=payload)


# Rate limit handler
def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content=format_response(False, None, "Too many requests"),
    )

app.add_exception_handler(RateLimitExceeded, rate_limit_handler)


# Startup
@app.on_event("startup")
def startup():
    logger.info("Application started (%s)", APP_ENV)
    import shutil
    if not shutil.which("ffmpeg"):
        logger.warning("ffmpeg not found")
    init_indexes()


# Shutdown
@app.on_event("shutdown")
def shutdown():
    logger.info("Application shutdown")


# Auth token
@app.post("/api/auth/token")
@limiter.limit("10/minute")
def issue_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    if not verify_demo_user(form_data.username, form_data.password):
        raise_api_error(status.HTTP_401_UNAUTHORIZED, "AUTH_ERROR", "Invalid credentials")

    access_token = create_access_token(subject=form_data.username)

    return format_response(True, {
        "access_token": access_token,
        "token_type": "bearer",
    })


@app.get("/")
def root():
    return {"status": "ok"}

@app.get("/health")
def health_endpoint():
    return {"status": "ok"}

# Routers
app.include_router(health.router)
app.include_router(audio.router)
app.include_router(auth_router)
app.include_router(conversations_router)