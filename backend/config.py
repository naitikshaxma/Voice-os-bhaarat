import os
from pathlib import Path
from dotenv import load_dotenv

env_path = Path(__file__).parent / ".env"
load_dotenv(dotenv_path=env_path)

APP_ENV = os.getenv("ENV", "development").strip().lower()
IS_DEV_ENV = APP_ENV in {"development", "dev", "local", "test"}

# API / IO
MAX_AUDIO_BYTES = int(os.getenv("MAX_AUDIO_BYTES", str(5 * 1024 * 1024)))
UPLOAD_CHUNK_BYTES = int(os.getenv("UPLOAD_CHUNK_BYTES", str(64 * 1024)))
ALLOWED_AUDIO_MIME_TYPES = {
    "audio/wav",
    "audio/x-wav",
    "audio/mpeg",
    "audio/mp3",
    "audio/webm",
    "video/webm",
}

# Security / Auth / DB
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
REQUIRE_AUTH = os.getenv("REQUIRE_AUTH", "true").strip().lower() in {"1", "true", "yes", "on"}
JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", "").strip()
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256").strip() or "HS256"
JWT_EXPIRE_MINUTES = int(os.getenv("JWT_EXPIRE_MINUTES", "60"))

if REQUIRE_AUTH and not JWT_SECRET_KEY and IS_DEV_ENV:
    REQUIRE_AUTH = False

DEMO_USERNAME = os.getenv("DEMO_AUTH_USERNAME", "demo" if IS_DEV_ENV else "")
DEMO_PASSWORD = os.getenv("DEMO_AUTH_PASSWORD", "demo123" if IS_DEV_ENV else "")

# Input validation
MAX_TEXT_LENGTH = int(os.getenv("MAX_TEXT_LENGTH", "300"))

# Intent / confidence
INTENT_CONFIDENCE_THRESHOLD = float(os.getenv("INTENT_CONFIDENCE_THRESHOLD", "0.35"))
LOW_CONFIDENCE_FALLBACK_THRESHOLD = float(os.getenv("LOW_CONFIDENCE_FALLBACK_THRESHOLD", "0.5"))
CONFIDENCE_HIGH_THRESHOLD = 0.75
CONFIDENCE_MEDIUM_THRESHOLD = 0.50

# Retrieval tuning
RAG_MATCH_THRESHOLD = int(os.getenv("RAG_MATCH_THRESHOLD", "75"))
RAG_SINGLE_TOKEN_OVERLAP_THRESHOLD = int(os.getenv("RAG_SINGLE_TOKEN_OVERLAP_THRESHOLD", "85"))
RAG_TOP_K = int(os.getenv("RAG_TOP_K", "3"))

# Lightweight context use from session memory
MAX_CONTEXT_MESSAGES = int(os.getenv("MAX_CONTEXT_MESSAGES", "2"))
PIPELINE_TIMEOUT_MS = int(os.getenv("PIPELINE_TIMEOUT_MS", "8000"))
STT_TIMEOUT_SECONDS = float(os.getenv("STT_TIMEOUT_SECONDS", "10.0"))
TTS_TIMEOUT_SECONDS = float(os.getenv("TTS_TIMEOUT_SECONDS", "8.0"))
PIPELINE_TIMEOUT_SECONDS = float(os.getenv("PIPELINE_TIMEOUT_SECONDS", "30.0"))

# Fallback replies (multilingual safe defaults)
FALLBACK_RESPONSES = {
    "en": {
        "confirmation": "Sorry, I could not identify the correct scheme.",
        "explanation": "Please provide more details.",
        "next_step": "",
    },
    "hi": {
        "confirmation": "माफ़ कीजिये, मैं सही योजना पहचान नहीं पाया।",
        "explanation": "कृपया थोड़ा और विवरण दें।",
        "next_step": "",
    },
}
