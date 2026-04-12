import json
import logging
import time
from contextvars import ContextVar
from threading import Lock
from typing import Any, Dict, Optional

_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="n/a")
_session_id_ctx: ContextVar[str] = ContextVar("session_id", default="n/a")

_metrics_lock = Lock()
_metrics: Dict[str, Any] = {
    "total_requests": 0,
    "total_response_time_ms": 0.0,
    "endpoints": {},
}


class RequestContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = _request_id_ctx.get()
        if not hasattr(record, "session_id"):
            record.session_id = _session_id_ctx.get()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "level": record.levelname,
            "message": record.getMessage(),
            "logger": record.name,
            "request_id": getattr(record, "request_id", "n/a"),
            "session_id": getattr(record, "session_id", "n/a"),
        }

        # Keep useful structured extras when provided.
        for key in ["method", "endpoint", "status_code", "response_time_ms", "event", "count"]:
            if hasattr(record, key):
                payload[key] = getattr(record, key)

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    if getattr(root, "_voice_os_json_configured", False):
        return

    log_level = getattr(logging, (level or "INFO").upper(), logging.INFO)
    root.setLevel(log_level)

    handler = logging.StreamHandler()
    handler.setLevel(log_level)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RequestContextFilter())

    root.handlers = [handler]
    root._voice_os_json_configured = True  # type: ignore[attr-defined]


def set_request_context(request_id: str, session_id: Optional[str] = None) -> None:
    _request_id_ctx.set(request_id or "n/a")
    if session_id:
        _session_id_ctx.set(session_id)


def set_session_context(session_id: Optional[str]) -> None:
    _session_id_ctx.set((session_id or "").strip() or "n/a")


def clear_request_context() -> None:
    _request_id_ctx.set("n/a")
    _session_id_ctx.set("n/a")


def record_request_metric(endpoint: str, response_time_ms: float) -> None:
    safe_endpoint = endpoint or "unknown"
    with _metrics_lock:
        _metrics["total_requests"] += 1
        _metrics["total_response_time_ms"] += max(float(response_time_ms), 0.0)
        endpoints = _metrics["endpoints"]
        endpoints[safe_endpoint] = int(endpoints.get(safe_endpoint, 0)) + 1


def get_metrics_snapshot() -> Dict[str, Any]:
    with _metrics_lock:
        total_requests = int(_metrics["total_requests"])
        total_time = float(_metrics["total_response_time_ms"])
        avg = (total_time / total_requests) if total_requests > 0 else 0.0
        return {
            "total_requests": total_requests,
            "avg_response_time_ms": round(avg, 2),
            "endpoints": dict(_metrics["endpoints"]),
        }
