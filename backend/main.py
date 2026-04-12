import time
import os
import logging
import re
import uuid
from time import perf_counter
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from fastapi.security import OAuth2PasswordRequestForm
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from .bert_service import get_intent_model_status, predict_intent
from .flow_engine import generate_response
from .observability import (
    clear_request_context,
    configure_logging,
    get_metrics_snapshot,
    record_request_metric,
    set_request_context,
    set_session_context,
)
from .rag_service import get_rag_status
from .security import (
    MAX_TEXT_LENGTH,
    create_access_token,
    get_optional_current_user,
    sanitize_text,
    verify_demo_user,
)
from .session_manager import append_conversation, get_conversation_history, get_or_create_session, update_session
from .session_manager import get_session_debug_snapshot
from .tts_service import generate_tts
from .whisper_service import DEFAULT_TRANSCRIBE_LANGUAGE, get_whisper_status, transcribe_audio, warmup_whisper

app = FastAPI(title="Voice OS Bharat")
configure_logging(level=os.getenv("LOG_LEVEL", "INFO"))
logger = logging.getLogger("voice_os_bharat")
APP_ENV = os.getenv("ENV", "development").strip().lower()

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter


@app.exception_handler(RateLimitExceeded)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded):
    logger.warning("rate_limit_exceeded path=%s request_id=%s", request.url.path, getattr(request.state, "request_id", "n/a"))
    return JSONResponse(status_code=429, content={"error": "Rate limit exceeded. Please try again later."})

MAX_AUDIO_BYTES = 5 * 1024 * 1024
ALLOWED_AUDIO_MIME_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/webm",
    "video/webm",
}

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8080",
        "http://127.0.0.1:8080",
    ],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "User-Agent"],
)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    request.state.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    request.state.session_id = ""
    set_request_context(request_id=request.state.request_id)

    started = perf_counter()
    response = None
    try:
        response = await call_next(request)
    except Exception:
        elapsed_ms = (perf_counter() - started) * 1000.0
        record_request_metric(request.url.path, elapsed_ms)
        logger.error(
            "request_failed",
            extra={
                "event": "request",
                "method": request.method,
                "endpoint": request.url.path,
                "status_code": 500,
                "response_time_ms": round(elapsed_ms, 2),
            },
        )
        raise
    finally:
        if response is not None:
            elapsed_ms = (perf_counter() - started) * 1000.0
            record_request_metric(request.url.path, elapsed_ms)
            logger.info(
                "request_completed",
                extra={
                    "event": "request",
                    "method": request.method,
                    "endpoint": request.url.path,
                    "status_code": response.status_code,
                    "response_time_ms": round(elapsed_ms, 2),
                },
            )

            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-Request-ID"] = request.state.request_id

        clear_request_context()

    return response


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception(
        "Unhandled exception on path %s request_id=%s",
        request.url.path,
        getattr(request.state, "request_id", "n/a"),
    )
    return JSONResponse(status_code=500, content={"error": "Something went wrong"})


@app.on_event("startup")
def startup() -> None:
    warmup_whisper()


@app.get("/health")
def health() -> dict:
    return {
        "status": "healthy",
        "whisper": get_whisper_status(),
        "intent_model": get_intent_model_status(),
        "rag": get_rag_status(),
    }


def _debug_print(label: str, value: object) -> None:
    safe_value = str(value).encode("unicode_escape").decode("ascii")
    logger.info("debug_event", extra={"event": label.strip(":"), "count": safe_value})


class IntentRequest(BaseModel):
    text: str


class TTSRequest(BaseModel):
    text: str
    language: str = "en"


def _validate_language(language: str) -> str:
    lang = (language or "").strip()
    if not lang:
        return DEFAULT_TRANSCRIBE_LANGUAGE
    if len(lang) > 15:
        return DEFAULT_TRANSCRIBE_LANGUAGE
    if not re.fullmatch(r"[A-Za-z_-]+", lang):
        return DEFAULT_TRANSCRIBE_LANGUAGE
    return lang


def _validate_text_input(text: str) -> str:
    cleaned = sanitize_text(text)
    if not cleaned:
        raise HTTPException(status_code=400, detail="Text payload is empty.")
    if len(cleaned) > MAX_TEXT_LENGTH:
        raise HTTPException(status_code=400, detail=f"Text payload exceeds {MAX_TEXT_LENGTH} characters.")
    return cleaned


def _validate_audio_upload(audio: UploadFile, audio_bytes: bytes) -> None:
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail=f"Audio payload is too large. Max allowed is {MAX_AUDIO_BYTES // (1024 * 1024)}MB.")
    content_type = (audio.content_type or "").lower().strip()
    if content_type and content_type not in ALLOWED_AUDIO_MIME_TYPES:
        allowed_types = ", ".join(sorted(ALLOWED_AUDIO_MIME_TYPES))
        raise HTTPException(status_code=400, detail=f"Unsupported audio format. Allowed MIME types: {allowed_types}")


@app.post("/api/auth/token")
@limiter.limit("10/minute")
def issue_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends()) -> dict:
    if not verify_demo_user(form_data.username, form_data.password):
        logger.warning(
            "auth_login_failed user=%s request_id=%s",
            form_data.username,
            getattr(request.state, "request_id", "n/a"),
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    access_token = create_access_token(subject=form_data.username)
    logger.info(
        "auth_login_success user=%s request_id=%s",
        form_data.username,
        getattr(request.state, "request_id", "n/a"),
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
    }


def _response_text_to_message(response_text: dict) -> str:
    return " ".join(
        [response_text.get("confirmation", ""), response_text.get("explanation", ""), response_text.get("next_step", "")]
    ).strip()


def _process_transcript(transcript: str, user_id: str, language: str, session_id: Optional[str] = None) -> dict:
    resolved_session_id, _ = get_or_create_session(session_id=session_id, user_id=user_id)
    set_session_context(resolved_session_id)
    _, conversation_history = get_conversation_history(session_id=resolved_session_id, user_id=user_id)
    logger.info(
        "conversation_history_loaded",
        extra={"event": "session", "session_id": resolved_session_id, "count": len(conversation_history)},
    )

    response_text, intent, confidence = generate_response(language=language, transcript=transcript)

    tts_input = " ".join(
        [response_text.get("confirmation", ""), response_text.get("explanation", ""), response_text.get("next_step", "")]
    ).strip()
    audio_base64 = generate_tts(tts_input, language)
    if not audio_base64:
        raise HTTPException(status_code=500, detail="TTS generation failed.")

    update_session(
        user_id,
        {
            "intent": intent,
            "transcript": transcript,
            "confidence": round(float(confidence) * 100.0, 2),
            "timestamp": time.time(),
        },
    )

    assistant_text = _response_text_to_message(response_text)
    resolved_session_id = append_conversation(
        session_id=resolved_session_id,
        user_id=user_id,
        user_text=transcript,
        assistant_text=assistant_text,
    )
    _, updated_history = get_conversation_history(session_id=resolved_session_id, user_id=user_id)

    return {
        "session_id": resolved_session_id,
        "conversation_length": len(updated_history),
        "session_active": True,
        "transcript": transcript,
        "intent": intent,
        "confidence": round(float(confidence) * 100.0, 2),
        "response_text": response_text,
        "audio_base64": f"data:audio/mp3;base64,{audio_base64}",
    }


@app.post("/api/transcribe")
@limiter.limit("20/minute")
async def transcribe(
    request: Request,
    audio: UploadFile = File(...),
    language: str = Form("hi"),
    session_id: str = Form(""),
    current_user: Optional[str] = Depends(get_optional_current_user),
) -> dict:
    _ = current_user
    audio_bytes = await audio.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Audio payload is empty.")
    _validate_audio_upload(audio, audio_bytes)

    suffix = Path(audio.filename or "input.webm").suffix or ".webm"
    safe_language = _validate_language(language)
    transcript = transcribe_audio(audio_bytes, language=safe_language, source_suffix=suffix)
    if not transcript:
        raise HTTPException(status_code=400, detail="Could not transcribe audio.")
    resolved_session_id, record = get_or_create_session(session_id=session_id)
    request.state.session_id = resolved_session_id
    set_session_context(resolved_session_id)

    _debug_print("Transcript:", transcript)
    return {
        "session_id": resolved_session_id,
        "conversation_length": len(record.get("history", [])),
        "session_active": True,
        "transcript": transcript,
        "language": language,
    }


@app.post("/api/intent")
@limiter.limit("40/minute")
def detect_intent(request: Request, payload: IntentRequest) -> dict:
    _ = request
    intent, confidence = predict_intent(payload.text)
    _debug_print("Detected intent:", intent)
    _debug_print("Confidence:", confidence)
    return {
        "intent": intent,
        "confidence": round(float(confidence) * 100.0, 2),
    }


@app.get("/api/metrics")
@limiter.limit("60/minute")
def metrics(request: Request) -> dict:
    _ = request
    return get_metrics_snapshot()


@app.post("/api/tts")
@limiter.limit("30/minute")
def synthesize(request: Request, payload: TTSRequest) -> dict:
    _ = request
    text = _validate_text_input(payload.text)
    safe_language = _validate_language(payload.language)

    audio_base64 = generate_tts(text, safe_language)
    if not audio_base64:
        raise HTTPException(status_code=500, detail="TTS generation failed.")

    return {"audio_base64": f"data:audio/mp3;base64,{audio_base64}"}


@app.post("/api/process-text")
@limiter.limit("30/minute")
def process_text(
    request: Request,
    text: str = Form(...),
    user_id: str = Form(...),
    language: str = Form("en"),
    session_id: str = Form(""),
) -> dict:
    transcript = _validate_text_input(text)
    safe_language = _validate_language(language)

    _debug_print("Frontend transcript:", transcript)
    return _process_transcript(
        transcript=transcript,
        user_id=user_id,
        language=safe_language,
        session_id=session_id,
    )


@app.post("/api/process-audio")
@limiter.limit("20/minute")
async def process_audio(
    request: Request,
    audio: Optional[UploadFile] = File(None),
    text: str = Form(""),
    user_id: str = Form(...),
    language: str = Form("en"),
    session_id: str = Form(""),
    current_user: Optional[str] = Depends(get_optional_current_user),
) -> dict:
    _ = current_user
    try:
        safe_language = _validate_language(language)
        transcript = sanitize_text(text)
        if len(transcript) > MAX_TEXT_LENGTH:
            raise HTTPException(status_code=400, detail=f"Text payload exceeds {MAX_TEXT_LENGTH} characters.")
        if transcript:
            _debug_print("Frontend transcript:", transcript)
            return _process_transcript(
                transcript=transcript,
                user_id=user_id,
                language=safe_language,
                session_id=session_id,
            )

        if audio is None:
            raise HTTPException(status_code=400, detail="Either text or audio is required.")

        audio_bytes = await audio.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Audio payload is empty.")
        _validate_audio_upload(audio, audio_bytes)

        suffix = Path(audio.filename or "input.webm").suffix or ".webm"
        transcript = transcribe_audio(audio_bytes, language=safe_language, source_suffix=suffix)
        if not transcript:
            raise HTTPException(status_code=400, detail="Could not transcribe audio.")
        _debug_print("Transcript:", transcript)

        return _process_transcript(
            transcript=transcript,
            user_id=user_id,
            language=safe_language,
            session_id=session_id,
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to process audio request request_id=%s", getattr(request.state, "request_id", "n/a"))
        raise HTTPException(status_code=500, detail="Something went wrong") from exc


if APP_ENV == "development":

    @app.get("/api/debug/session/{session_id}")
    def debug_session(session_id: str) -> dict:
        snapshot = get_session_debug_snapshot(session_id)
        if snapshot is None:
            raise HTTPException(status_code=404, detail="Session not found")
        return snapshot
