import logging
from typing import Optional
from time import perf_counter

from fastapi import APIRouter, Depends, Form, Request, status, HTTPException
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..security import get_current_user
from ..session_manager import migrate_session_owner
from ..config import PIPELINE_TIMEOUT_SECONDS
from ..services.pipeline_service import process_user_input
from ..tts_service import generate_tts
from ..api_utils import (
    format_response,
    raise_api_error,
    run_blocking_with_timeout,
    validate_language,
    validate_text_input,
)

logger = logging.getLogger("voice_os_bharat.routers.process")
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


def _process_transcript(
    transcript: str,
    user_id: str,
    language: str,
    session_id: Optional[str] = None,
    telemetry: Optional[dict] = None,
) -> dict:
    payload = process_user_input(
        user_id=user_id,
        session_id=session_id,
        language=language,
        transcript=transcript,
        telemetry=telemetry,
    )
    return payload


@router.post("/api/process-text")
@limiter.limit("10/minute")
async def process_text(
    request: Request,
    text: str = Form(""),
    user_id: str = Form(...),
    language: str = Form("en"),
    session_id: str = Form(""),
    current_user: Optional[str] = Depends(get_current_user),
) -> dict:
    _ = current_user
    telemetry: dict = {}
    try:
        safe_language = validate_language(language)
        transcript = validate_text_input(text)

        effective_user_id = (current_user or "").strip() or (user_id or "").strip()
        if not effective_user_id:
            raise_api_error(status.HTTP_401_UNAUTHORIZED, "AUTH_ERROR", "Missing user identity")

        if current_user and user_id and session_id and user_id != current_user:
            migrate_session_owner(session_id=session_id, old_user_id=user_id, new_user_id=current_user)

        payload = await run_blocking_with_timeout(
            _process_transcript,
            transcript,
            effective_user_id,
            safe_language,
            session_id,
            telemetry=telemetry,
            timeout_seconds=PIPELINE_TIMEOUT_SECONDS,
            error_code="PIPELINE_TIMEOUT",
            timeout_message="Request processing timed out.",
        )
        
        final_data = {
            "response_text": payload.get("response_text", ""),
            "audio_base64": payload.get("audio_base64", ""),
            "confidence": payload.get("confidence", 0.0),
            "session_id": payload.get("session_id", ""),
            "scheme": payload.get("scheme", "")
        }
        return format_response(True, final_data)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to process text request request_id=%s", getattr(request.state, "request_id", "n/a"))
        raise_api_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "PIPELINE_ERROR", "Something went wrong")

@router.post("/api/tts")
@limiter.limit("20/minute")
async def process_tts(
    request: Request,
    text: str = Form(...),
    language: str = Form("en"),
) -> dict:
    try:
        audio_base64 = generate_tts(text, language)
        return format_response(True, {"audio_base64": audio_base64})
    except Exception as exc:
        logger.exception("Failed to generate TTS")
        raise_api_error(status.HTTP_500_INTERNAL_SERVER_ERROR, "TTS_ERROR", "Failed to generate TTS")
