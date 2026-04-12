import os
import time
import uuid
import logging
from typing import Dict, List, Optional, Tuple

SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "1800"))
MAX_HISTORY_MESSAGES = int(os.getenv("SESSION_MAX_MESSAGES", "10"))
MAX_TOTAL_SESSIONS = int(os.getenv("SESSION_MAX_TOTAL", "1000"))
CLEANUP_INTERVAL_SECONDS = int(os.getenv("SESSION_CLEANUP_INTERVAL_SECONDS", "30"))

_sessions: Dict[str, dict] = {}
_last_cleanup_at = 0.0
logger = logging.getLogger("voice_os_bharat.session")


def _now() -> float:
    return time.time()


def _normalize_session_id(session_id: Optional[str]) -> str:
    value = (session_id or "").strip()
    if value:
        try:
            return str(uuid.UUID(value))
        except (ValueError, TypeError):
            logger.warning("session_invalid_id supplied=%s action=regenerate", value)
    return str(uuid.uuid4())


def _evict_if_over_capacity() -> None:
    if len(_sessions) <= MAX_TOTAL_SESSIONS:
        return
    remove_count = len(_sessions) - MAX_TOTAL_SESSIONS
    ordered = sorted(_sessions.items(), key=lambda item: float(item[1].get("last_active_at", item[1].get("created_at", 0))))
    for sid, _ in ordered[:remove_count]:
        _sessions.pop(sid, None)
        logger.warning("session_evicted session_id=%s reason=capacity_limit", sid)


def _cleanup_expired_sessions(force: bool = False) -> None:
    global _last_cleanup_at
    current = _now()
    if not force and current - _last_cleanup_at < CLEANUP_INTERVAL_SECONDS:
        return
    _last_cleanup_at = current

    expired = [
        sid
        for sid, data in _sessions.items()
        if current - float(data.get("last_active_at", data.get("created_at", 0))) > SESSION_TTL_SECONDS
    ]
    for sid in expired:
        _sessions.pop(sid, None)
        logger.info("session_expired session_id=%s", sid)


def _create_session_record(session_id: str, user_id: Optional[str]) -> dict:
    current = _now()
    record = {
        "session_id": session_id,
        "user_id": (user_id or "").strip() or None,
        "created_at": current,
        "last_active_at": current,
        "history": [],
        "events": [],
    }
    _sessions[session_id] = record
    _evict_if_over_capacity()
    logger.info("session_created session_id=%s user_id_present=%s", session_id, bool(record.get("user_id")))
    return record


def _get_or_create_session_record(session_id: Optional[str], user_id: Optional[str] = None) -> Tuple[str, dict]:
    _cleanup_expired_sessions()
    resolved_session_id = _normalize_session_id(session_id)
    record = _sessions.get(resolved_session_id)
    normalized_user_id = (user_id or "").strip() or None

    if record is None:
        record = _create_session_record(resolved_session_id, normalized_user_id)
    else:
        bound_user_id = record.get("user_id")
        if bound_user_id and normalized_user_id and bound_user_id != normalized_user_id:
            logger.warning(
                "session_user_mismatch supplied_session_id=%s bound_user_id=%s supplied_user_id=%s action=create_new",
                resolved_session_id,
                bound_user_id,
                normalized_user_id,
            )
            resolved_session_id = str(uuid.uuid4())
            record = _create_session_record(resolved_session_id, normalized_user_id)
        elif normalized_user_id and not bound_user_id:
            record["user_id"] = normalized_user_id
            logger.info("session_user_bound session_id=%s", resolved_session_id)

        record["last_active_at"] = _now()
        logger.info("session_reused session_id=%s", resolved_session_id)
    return resolved_session_id, record


def get_or_create_session(session_id: Optional[str], user_id: Optional[str] = None) -> Tuple[str, dict]:
    return _get_or_create_session_record(session_id=session_id, user_id=user_id)


def get_conversation_history(session_id: Optional[str], user_id: Optional[str] = None) -> Tuple[str, List[dict]]:
    resolved_session_id, record = _get_or_create_session_record(session_id=session_id, user_id=user_id)
    return resolved_session_id, list(record.get("history", []))


def get_session_debug_snapshot(session_id: str) -> Optional[dict]:
    _cleanup_expired_sessions(force=True)
    normalized = _normalize_session_id(session_id)
    record = _sessions.get(normalized)
    if record is None:
        return None

    return {
        "session_id": record.get("session_id"),
        "user_id_present": bool(record.get("user_id")),
        "created_at": record.get("created_at"),
        "last_active_at": record.get("last_active_at"),
        "conversation_length": len(record.get("history", [])),
        "session_active": True,
        "history": list(record.get("history", [])),
    }


def append_conversation(session_id: Optional[str], user_id: Optional[str], user_text: str, assistant_text: str) -> str:
    resolved_session_id, record = _get_or_create_session_record(session_id=session_id, user_id=user_id)
    history = list(record.get("history", []))

    if user_text.strip():
        history.append({"role": "user", "text": user_text.strip()})
    if assistant_text.strip():
        history.append({"role": "assistant", "text": assistant_text.strip()})

    if len(history) > MAX_HISTORY_MESSAGES:
        history = history[-MAX_HISTORY_MESSAGES:]

    record["history"] = history
    record["last_active_at"] = _now()
    return resolved_session_id


# Backward-compatible wrappers for existing usage patterns.
def get_session(user_id):
    _, record = _get_or_create_session_record(session_id=user_id, user_id=user_id)
    return record


def update_session(user_id, data):
    _, record = _get_or_create_session_record(session_id=user_id, user_id=user_id)
    events = list(record.get("events", []))
    events.append(data)
    if len(events) > MAX_HISTORY_MESSAGES:
        events = events[-MAX_HISTORY_MESSAGES:]
    record["events"] = events
    record["last_active_at"] = _now()
