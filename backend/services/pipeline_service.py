"""
pipeline_service.py — Unified orchestration pipeline for Voice OS Bharat.

Coordinates conversation state, flow_engine execution, and TTS generation.
Simplified to use dataset-driven logic without heavy ML models.
"""
import logging
import re
import uuid
from time import perf_counter
from typing import Optional

from ..config import FALLBACK_RESPONSES, PIPELINE_TIMEOUT_MS, TTS_TIMEOUT_SECONDS
from ..flow_engine import generate_response
from ..session_manager import (
    append_conversation,
    get_or_create_session_with_meta,
    update_session_metadata,
)
from ..tts_service import generate_tts
from ..routers.conversations_router import upsert_conversation

logger = logging.getLogger("voice_os_bharat.pipeline")


SAFE_ERROR_RESPONSES = {
    "en": {
        "confirmation": "Which scheme would you like to know about?",
        "explanation": "",
        "next_step": "",
    },
    "hi": {
        "confirmation": "आप किस स्कीम के बारे में जानना चाहते हैं?",
        "explanation": "",
        "next_step": "",
    },
}

_RESPONSE_CACHE = {}
_CACHE_MAX = 500


def _to_message(response_text: dict) -> str:
    return " ".join(
        [response_text.get("confirmation", ""), response_text.get("explanation", ""), response_text.get("next_step", "")]
    ).strip()


def _normalize_line(text: object) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip())


def _ensure_two_line_response(response_text: dict, language: str) -> dict:
    lang = "hi" if (language or "").strip().lower() == "hi" else "en"
    fallback = SAFE_ERROR_RESPONSES[lang]
    
    line_1 = _normalize_line(response_text.get("confirmation", ""))
    line_2 = _normalize_line(response_text.get("explanation", ""))
    line_2_alt = _normalize_line(response_text.get("next_step", ""))

    if not line_1:
        line_1 = _normalize_line(fallback.get("confirmation", ""))
    if not line_2:
        line_2 = line_2_alt or _normalize_line(fallback.get("explanation", ""))

    return {
        "confirmation": line_1,
        "explanation": line_2,
        "next_step": "",
    }


def _record_timing(telemetry: Optional[dict], key: str, value_ms: float) -> None:
    if telemetry is None:
        return
    telemetry[key] = round(float(telemetry.get(key, 0.0)) + max(float(value_ms), 0.0), 2)


def process_user_input(
    user_id: str,
    session_id: Optional[str],
    language: str,
    transcript: str,
    telemetry: Optional[dict] = None,
) -> dict:
    """
    Main pipeline entry point.
    Executes scheme detection, state management, and TTS generation.
    """
    pipeline_started = perf_counter()
    if telemetry is None:
        telemetry = {}

    safe_transcript = str(transcript or "").strip()
    language_used = "hi" if (language or "").strip().lower() == "hi" else "en"

    fallback_used = False
    fallback_reason = ""
    intent = "unknown"
    confidence = 0.0
    response_text = SAFE_ERROR_RESPONSES[language_used]
    audio_base64 = ""
    
    resolved_session_id = session_id

    try:
        # 1. Session Setup
        session_meta = {}
        if resolved_session_id:
            resolved_session_id, session_record, _ = get_or_create_session_with_meta(resolved_session_id, user_id)
        else:
            resolved_session_id = uuid.uuid4().hex
            _, session_record, _ = get_or_create_session_with_meta(resolved_session_id, user_id)

        prior_scheme_name = session_record.get("metadata", {}).get("last_scheme_name", "")

        # 2. Check Cache
        cache_key = f"{language_used}:{safe_transcript}:{prior_scheme_name}"
        if cache_key in _RESPONSE_CACHE:
            cached_data = _RESPONSE_CACHE[cache_key]
            response_text = cached_data["response_text"]
            intent = cached_data["intent"]
            confidence = cached_data["confidence"]
            matched_scheme = cached_data["matched_scheme"]
            if intent == "unknown":
                fallback_used = True
                fallback_reason = "no_match"
        else:
            # 3. Flow Engine Execution
            generated_text, generated_intent, generated_confidence, top_k = generate_response(
                language=language_used,
                transcript=safe_transcript,
                last_scheme=prior_scheme_name,
                telemetry=telemetry,
            )

            response_text = generated_text
            intent = generated_intent
            confidence = float(generated_confidence)
            matched_scheme = top_k[0] if top_k else None

            if intent == "unknown":
                fallback_used = True
                fallback_reason = "no_match"
                
            if len(_RESPONSE_CACHE) > _CACHE_MAX:
                _RESPONSE_CACHE.clear()
            _RESPONSE_CACHE[cache_key] = {
                "response_text": response_text,
                "intent": intent,
                "confidence": confidence,
                "matched_scheme": matched_scheme
            }

        # 4. Update Session Context
        if intent == "scheme_query" and matched_scheme:
            update_session_metadata(
                session_id=resolved_session_id,
                user_id=user_id,
                last_scheme_name=matched_scheme,
            )

    except Exception:
        logger.exception("pipeline_generation_failed", extra={"event": "pipeline_error"})
        fallback_used = True
        fallback_reason = "error"
        intent = "unknown"
        confidence = 0.0
        response_text = SAFE_ERROR_RESPONSES[language_used]

    # Ensure response formatting
    response_text = _ensure_two_line_response(response_text=response_text, language=language_used)
    assistant_text = _to_message(response_text)

    # 4. TTS Generation (Fire & Forget with Timeout)
    tts_started = perf_counter()
    tts_text = assistant_text[:400] # trim text before TTS
    try:
        import concurrent.futures as _cf
        with _cf.ThreadPoolExecutor(max_workers=1) as _exec:
            _fut = _exec.submit(generate_tts, tts_text, language_used)
            try:
                # Disable TTS if slow (configurable timeout)
                audio_base64_result = _fut.result(timeout=TTS_TIMEOUT_SECONDS)
                if audio_base64_result:
                    audio_base64 = audio_base64_result
            except _cf.TimeoutError:
                logger.warning("tts_timeout — skipping audio, returning text only")
                audio_base64 = ""
    except Exception as e:
        logger.warning(f"tts_error: {e}")
        audio_base64 = ""
    _record_timing(telemetry, "tts_time_ms", (perf_counter() - tts_started) * 1000.0)

    # 5. Save Conversation History (Fire & Forget)
    def _save_history():
        try:
            append_conversation(
                session_id=resolved_session_id,
                user_id=user_id,
                user_text=safe_transcript,
                assistant_text=assistant_text,
            )
        except Exception as e:
            logger.error(f"Failed to append conversation: {e}")

        try:
            upsert_conversation(
                session_id=resolved_session_id,
                user_id=user_id,
                user_text=safe_transcript,
                assistant_text=assistant_text,
            )
        except Exception as e:
            logger.error(f"Failed to upsert conversation: {e}")
            
    import threading
    threading.Thread(target=_save_history).start()

    elapsed_ms = (perf_counter() - pipeline_started) * 1000.0
    _record_timing(telemetry, "pipeline_time_ms", elapsed_ms)

    # 6. Final Payload
    log_payload = {
        "query": safe_transcript,
        "fallback_used": fallback_used,
        "confidence": confidence,
        "latency_ms": int(elapsed_ms),
    }
    logger.info("PIPELINE_FINAL_LOG: %s", log_payload)

    return {
        "session_id": resolved_session_id,
        "response_text": response_text,
        "audio_base64": audio_base64,
        "confidence": confidence,
        "confidence_level": "high" if confidence > 0.7 else "low",
        "intent": intent,
        "fallback_used": fallback_used,
        "fallback_reason": fallback_reason,
        "source": "engine",
        "language_used": language_used,
        "normalized_language": language_used,
        "telemetry": telemetry,
    }
