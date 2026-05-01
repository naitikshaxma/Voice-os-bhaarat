import os
import uuid
import logging
from datetime import datetime
from typing import List, Optional, Tuple
from fastapi import HTTPException
from pymongo import ReturnDocument

from .db.mongo import sessions_collection
from .db.mongo import conversations_collection

MAX_HISTORY_MESSAGES = int(os.getenv("SESSION_MAX_MESSAGES", "20"))
MAX_TOTAL_SESSIONS = int(os.getenv("SESSION_MAX_TOTAL", "1000"))

logger = logging.getLogger("voice_os_bharat.session")

def _normalize_session_id(session_id: Optional[str]) -> str:
    value = (session_id or "").strip()
    if value:
        try:
            return str(uuid.UUID(value))
        except (ValueError, TypeError):
            logger.warning("session_invalid_id supplied=%s action=regenerate", value)
    return str(uuid.uuid4())

def _get_or_create_session_record(session_id: Optional[str], user_id: Optional[str] = None) -> Tuple[str, dict]:
    resolved_session_id = _normalize_session_id(session_id)
    normalized_user_id = (user_id or "").strip() or None

    # Verify session ownership FIRST if session already exists
    existing = sessions_collection.find_one({"session_id": resolved_session_id})
    if existing:
        if existing.get("user_id") and normalized_user_id and existing["user_id"] != normalized_user_id:
            logger.warning("session_security_violation session=%s user=%s", resolved_session_id, normalized_user_id)
            raise HTTPException(status_code=403, detail="Forbidden session access")

    record = sessions_collection.find_one_and_update(
        {"session_id": resolved_session_id, "user_id": normalized_user_id},
        {
            "$setOnInsert": {
                "messages": [],
                "metadata": {},
                "created_at": datetime.utcnow()
            },
            "$set": {
                "last_active_at": datetime.utcnow()
            }
        },
        upsert=True,
        return_document=ReturnDocument.AFTER
    )

    if "_id" in record:
        record["_id"] = str(record["_id"])
        
    return resolved_session_id, record

def get_or_create_session(session_id: Optional[str], user_id: Optional[str] = None) -> Tuple[str, dict]:
    return _get_or_create_session_record(session_id=session_id, user_id=user_id)

def get_or_create_session_with_meta(session_id: Optional[str], user_id: Optional[str] = None) -> Tuple[str, dict, bool]:
    resolved_session_id, record = _get_or_create_session_record(session_id=session_id, user_id=user_id)
    # The record from mongo doesn't naturally track 'reused_session', defaulting to True for API stability
    return resolved_session_id, record, True

def get_conversation_history(session_id: Optional[str], user_id: Optional[str] = None) -> Tuple[str, List[dict]]:
    resolved_session_id, record = _get_or_create_session_record(session_id=session_id, user_id=user_id)
    # Return from "messages" to match the updated prompt instructions, but fallback to "history" to prevent pipeline breaks
    return resolved_session_id, list(record.get("messages", record.get("history", [])))


def append_conversation(session_id: Optional[str], user_id: Optional[str], user_text: str, assistant_text: str) -> str:
    resolved_session_id, _ = _get_or_create_session_record(session_id=session_id, user_id=user_id)
    
    new_messages = []
    if user_text.strip():
        new_messages.append({"role": "user", "text": user_text.strip()})
    if assistant_text.strip():
        new_messages.append({"role": "assistant", "text": assistant_text.strip()})

    if new_messages:
        sessions_collection.update_one(
            {"session_id": resolved_session_id},
            {
                "$push": {
                    "messages": {
                        "$each": new_messages,
                        "$slice": -20
                    }
                },
                "$set": {"last_active_at": datetime.utcnow()}
            }
        )
    return resolved_session_id

def get_session_metadata(session_id: Optional[str], user_id: Optional[str] = None) -> dict:
    _, record = _get_or_create_session_record(session_id=session_id, user_id=user_id)
    return dict(record.get("metadata", {}))

def update_session_metadata(session_id: Optional[str], user_id: Optional[str] = None, **metadata_updates) -> str:
    resolved_session_id, _ = _get_or_create_session_record(session_id=session_id, user_id=user_id)
    
    if metadata_updates:
        set_updates = {}
        unset_updates = {}
        for k, v in metadata_updates.items():
            if k is None:
                continue
            if v is None:
                unset_updates[f"metadata.{k}"] = ""
            else:
                set_updates[f"metadata.{k}"] = v
                
        update_doc = {"$set": {"last_active_at": datetime.utcnow()}}
        if set_updates:
            update_doc["$set"].update(set_updates)
        if unset_updates:
            update_doc["$unset"] = unset_updates
            
        sessions_collection.update_one({"session_id": resolved_session_id}, update_doc)
        
    return resolved_session_id


def migrate_session_owner(session_id: Optional[str], old_user_id: Optional[str], new_user_id: Optional[str]) -> bool:
    resolved_session_id = _normalize_session_id(session_id)
    old_id = (old_user_id or "").strip()
    new_id = (new_user_id or "").strip()
    if not resolved_session_id or not old_id or not new_id or old_id == new_id:
        return False

    updated_session = sessions_collection.update_one(
        {"session_id": resolved_session_id, "user_id": old_id},
        {"$set": {"user_id": new_id, "last_active_at": datetime.utcnow()}},
    )

    updated_convo = conversations_collection.update_one(
        {"session_id": resolved_session_id, "user_id": old_id},
        {"$set": {"user_id": new_id, "updated_at": datetime.utcnow()}},
    )

    return (updated_session.modified_count + updated_convo.modified_count) > 0

