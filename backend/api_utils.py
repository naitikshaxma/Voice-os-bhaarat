import asyncio
import functools
import logging
import re
from typing import Optional
from fastapi import HTTPException

from .config import MAX_TEXT_LENGTH
from .security import sanitize_text

logger = logging.getLogger("voice_os_bharat.api")


def format_response(success: bool, data: Optional[dict] = None, error: Optional[str] = None) -> dict:
    """Formats standard API response."""
    res = {"success": success, "data": data}
    if error is not None:
        res["error"] = error
    return res


def raise_api_error(status_code: int, error: str, message: str, details: Optional[object] = None) -> None:
    raise HTTPException(status_code=status_code, detail=format_response(False, None, message))


async def run_blocking_with_timeout(
    func,
    *args,
    timeout_seconds: float,
    error_code: str,
    timeout_message: str,
    **kwargs,
):
    loop = asyncio.get_running_loop()
    call = functools.partial(func, *args, **kwargs)
    try:
        return await asyncio.wait_for(loop.run_in_executor(None, call), timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        logger.warning("async_timeout function=%s timeout_seconds=%.2f", getattr(func, "__name__", "blocking_call"), timeout_seconds)
        raise_api_error(504, error_code, timeout_message, None)
    except HTTPException:
        raise


def validate_text_input(text: Optional[str]) -> str:
    if not text:
        raise_api_error(400, "VALIDATION_ERROR", "Text input is empty.")
    text = str(text)
    if len(text) > MAX_TEXT_LENGTH:
        raise_api_error(413, "VALIDATION_ERROR", f"Text exceeds maximum allowed length of {MAX_TEXT_LENGTH} characters.")
    clean_text = sanitize_text(text)
    if not clean_text:
        raise_api_error(400, "VALIDATION_ERROR", "Text contains invalid or empty content after sanitization.")
    return clean_text


def validate_language(lang_code: Optional[str]) -> str:
    lang = (lang_code or "").strip().lower()
    if lang not in ["hi", "en"]:
        logger.warning("invalid_language supplied=%s action=fallback_en", lang)
        return "en"
    return lang
