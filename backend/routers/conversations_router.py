"""
conversations_router.py — ChatGPT-style conversation history API.

Endpoints:
  GET  /api/conversations           → list all conversations for user (sorted latest first)
  GET  /api/conversations/{sid}     → full message history for one session
  DELETE /api/conversations/{sid}   → delete a conversation
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from slowapi import Limiter
from slowapi.util import get_remote_address

from ..api_utils import format_response, raise_api_error
from ..db.mongo import conversations_collection, serialize_doc
from ..security import get_current_user

logger = logging.getLogger("voice_os_bharat.conversations")
router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


def _generate_title(text: str) -> str:
    """First 6 words of user query → conversation title."""
    words = (text or "").strip().split()
    title = " ".join(words[:6])
    return (title[:60] + "…") if len(title) > 60 else title or "New Conversation"


def upsert_conversation(
    *,
    session_id: str,
    user_id: str,
    user_text: str,
    assistant_text: str,
) -> None:
    """
    Called by pipeline_service after each successful exchange.
    Atomically upserts the conversation document and appends both messages.
    """
    if not session_id or not user_id:
        return

    now = datetime.now(timezone.utc)
    title = _generate_title(user_text)

    user_msg = {"role": "user", "text": user_text, "timestamp": now}
    assistant_msg = {"role": "assistant", "text": assistant_text, "timestamp": now}

    try:
        conversations_collection.find_one_and_update(
            {"session_id": session_id, "user_id": user_id},
            {
                "$setOnInsert": {
                    "session_id": session_id,
                    "user_id": user_id,
                    "title": title,
                    "created_at": now,
                },
                "$set": {"updated_at": now},
                "$push": {
                    "messages": {
                        "$each": [user_msg, assistant_msg],
                        "$slice": -80,          # keep last 40 exchanges (80 msgs)
                    }
                },
                # Only update title from first message (via conditional logic below)
            },
            upsert=True,
            return_document=True,
        )
    except Exception:
        logger.exception(
            "conversation_upsert_failed session_id=%s user_id=%s", session_id, user_id
        )


# ─────────────────────────────────────────────
# GET /api/conversations
# ─────────────────────────────────────────────
@router.get("/api/conversations")
@limiter.limit("30/minute")
def list_conversations(
    request: Request,
    current_user: str = Depends(get_current_user),
) -> dict:
    """Returns all conversations for the authenticated user, latest first."""
    try:
        cursor = (
            conversations_collection
            .find(
                {"user_id": current_user},
                {"session_id": 1, "title": 1, "updated_at": 1, "_id": 0},
            )
            .sort("updated_at", -1)
            .limit(100)
        )
        results = []
        for doc in cursor:
            updated = doc.get("updated_at")
            results.append({
                "session_id": doc.get("session_id", ""),
                "title": doc.get("title", "New Conversation"),
                "updated_at": updated.isoformat() if updated else "",
            })
        return format_response(True, results)
    except Exception:
        logger.exception("list_conversations_failed user_id=%s", current_user)
        raise_api_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "DB_ERROR",
            "Failed to fetch conversations",
        )


# ─────────────────────────────────────────────
# GET /api/conversations/{session_id}
# ─────────────────────────────────────────────
@router.get("/api/conversations/{session_id}")
@limiter.limit("30/minute")
def get_conversation(
    request: Request,
    session_id: str,
    current_user: str = Depends(get_current_user),
) -> dict:
    """Returns full message history for a single session."""
    try:
        doc = conversations_collection.find_one(
            {"session_id": session_id, "user_id": current_user}
        )
        if not doc:
            raise_api_error(
                status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Conversation not found"
            )

        messages = []
        for m in doc.get("messages", []):
            ts = m.get("timestamp")
            messages.append({
                "role": m.get("role", "user"),
                "text": m.get("text", ""),
                "timestamp": ts.isoformat() if ts else "",
            })

        return format_response(True, {
            "session_id": doc.get("session_id"),
            "title": doc.get("title", "New Conversation"),
            "messages": messages,
            "created_at": doc["created_at"].isoformat() if doc.get("created_at") else "",
            "updated_at": doc["updated_at"].isoformat() if doc.get("updated_at") else "",
        })
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "get_conversation_failed session_id=%s user_id=%s", session_id, current_user
        )
        raise_api_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "DB_ERROR",
            "Failed to fetch conversation",
        )


# ─────────────────────────────────────────────
# DELETE /api/conversations/{session_id}
# ─────────────────────────────────────────────
@router.delete("/api/conversations/{session_id}")
@limiter.limit("20/minute")
def delete_conversation(
    request: Request,
    session_id: str,
    current_user: str = Depends(get_current_user),
) -> dict:
    """Deletes a conversation. Only owner can delete."""
    try:
        result = conversations_collection.delete_one(
            {"session_id": session_id, "user_id": current_user}
        )
        if result.deleted_count == 0:
            raise_api_error(
                status.HTTP_404_NOT_FOUND, "NOT_FOUND", "Conversation not found"
            )
        return format_response(True, {"deleted": session_id})
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "delete_conversation_failed session_id=%s user_id=%s", session_id, current_user
        )
        raise_api_error(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "DB_ERROR",
            "Failed to delete conversation",
        )
