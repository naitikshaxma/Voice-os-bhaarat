"""
flow_engine.py — Simplified, dataset-driven response generation.

Uses scheme_engine (keyword-based, no ML) for fast, reliable results.
"""
import logging
from time import perf_counter
from typing import Dict, List, Optional, Tuple

from .scheme_engine import get_scheme_response, detect_topic
from .config import FALLBACK_RESPONSES

logger = logging.getLogger("voice_os_bharat.flow")


def _record_timing(telemetry: Optional[dict], key: str, value_ms: float) -> None:
    if telemetry is None:
        return
    telemetry[key] = round(float(telemetry.get(key, 0.0)) + max(float(value_ms), 0.0), 2)


def _fallback(lang: str) -> dict:
    return dict(FALLBACK_RESPONSES.get(lang, FALLBACK_RESPONSES["en"]))


def generate_response(
    language: str,
    transcript: str,
    last_scheme: Optional[str] = None,
    telemetry: Optional[dict] = None,
) -> Tuple[dict, str, float, list]:
    """
    Returns (response_dict, intent_str, confidence_float, top_k_list).
    Never raises — always returns something usable.
    """
    lang = "hi" if (language or "").strip().lower() == "hi" else "en"
    query_text = (transcript or "").lower().strip()

    if not query_text:
        return _fallback(lang), "unknown", 0.0, []

    logger.info("flow_input query=%r lang=%s last_scheme=%r", query_text[:80], lang, last_scheme)

    t0 = perf_counter()
    response, matched_scheme, confidence = get_scheme_response(
        query=transcript,
        language=language,
        last_scheme=last_scheme,
    )
    _record_timing(telemetry, "engine_time_ms", (perf_counter() - t0) * 1000.0)

    if matched_scheme:
        logger.info("flow_match scheme=%r confidence=%.2f", matched_scheme, confidence)
        return response, "scheme_query", confidence, [matched_scheme]

    logger.warning("flow_no_match query=%r", query_text[:60])
    return _fallback(lang), "unknown", 0.0, []
