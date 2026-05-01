"""
scheme_engine.py — Lightweight dataset-driven scheme detection.

Replaces ML models + RAG with a fast keyword-score approach.
Loads directly from datasets/schemes_55.json — no training needed.
"""
import json
import logging
import os
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger("voice_os_bharat.scheme_engine")

# ── Paths ────────────────────────────────────────────────────────────────────
_DATASET_PATH = Path(__file__).parent.parent / "datasets" / "schemes_55.json"

# ── Stopwords to skip when building keyword sets ─────────────────────────────
_STOP = {
    "the", "a", "an", "and", "or", "of", "for", "in", "to", "by", "is",
    "are", "was", "with", "this", "that", "it", "its", "on", "at", "be",
    "ke", "ki", "ka", "ko", "me", "se", "hai", "hain", "aur", "ya", "kya",
    "kaise", "kab", "kahan", "main", "mera", "meri", "aapka", "apka",
    "batao", "bataiye", "jankari", "detail", "details", "about",
    "है", "क्या", "के", "की", "का", "को", "में", "से", "हैं", "और", "या",
    "कैसे", "कब", "कहाँ", "मैं", "मेरा", "मेरी", "आपका", "आपकी", "बताओ",
    "बताइये", "जानकारी", "योजना", "स्कीम", "साथ", "वाले", "वाली", "चाहिए"
}

# ── Topic keyword maps ────────────────────────────────────────────────────────
_ELIGIBILITY_KW = {
    "eligibility", "patarta", "eligible", "qualify", "qualified", "yogyata",
    "kaun", "who can", "criteria", "condition", "patr", "patra",
    "पात्रता", "योग्यता", "कौन", "कौन पात्र", "कौन eligible",
}
_DOCUMENTS_KW = {
    "document", "documents", "dastavez", "dastave", "kagaj", "papers", "required",
    "what do i need", "kya chahiye", "docs", "certificate",
    "दस्तावेज", "दस्तावेज़", "कागज़", "कागज", "प्रमाण", "आवश्यक",
}
_APPLY_KW = {
    "apply", "aavedan", "register", "registration", "form", "kaise kare",
    "kaise apply", "process", "steps", "procedure", "how to",
    "आवेदन", "अप्लाई", "रजिस्टर", "पंजीकरण", "प्रक्रिया", "कैसे करें",
}


def _tokenize(text: str) -> List[str]:
    """Lowercase, strip punctuation, split on whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s\u0900-\u097f]", " ", text)  # keep Devanagari
    return [t for t in text.split() if t and t not in _STOP and len(t) > 1]


def _build_scheme_keywords(scheme: dict) -> List[str]:
    """
    Auto-generate keyword list from a scheme dict.
    Uses: scheme_name, short_name, category, tags, query_variations.
    """
    kws: set = set()

    # 1. scheme_name words
    for tok in _tokenize(scheme.get("scheme_name", "")):
        kws.add(tok)

    # 2. short_name
    short = scheme.get("short_name", "").lower().strip()
    if short:
        kws.add(short)
        for tok in _tokenize(short):
            kws.add(tok)

    # 3. category
    for tok in _tokenize(scheme.get("category", "")):
        kws.add(tok)

    # 4. tags (list)
    for tag in scheme.get("tags", []):
        for tok in _tokenize(str(tag)):
            kws.add(tok)

    # 5. query_variations — highest signal
    for qv in scheme.get("query_variations", []):
        for tok in _tokenize(str(qv)):
            kws.add(tok)

    # 6. description snippets (first 100 chars)
    for field in ("description_en", "description_hi"):
        snippet = str(scheme.get(field, ""))[:120]
        for tok in _tokenize(snippet):
            kws.add(tok)

    # Remove generic noise and topic keywords to prevent false scheme matches
    kws -= {
        "scheme", "yojana", "pradhan", "mantri", "india", "government",
        "govt", "sarkar", "india", "pm", "national",
    }
    kws -= _ELIGIBILITY_KW
    kws -= _DOCUMENTS_KW
    kws -= _APPLY_KW
    
    return sorted(kws)


def _load() -> Tuple[List[dict], Dict[str, List[str]]]:
    with open(_DATASET_PATH, encoding="utf-8") as f:
        raw: List[dict] = json.load(f)

    keywords_map: Dict[str, List[str]] = {}
    for scheme in raw:
        key = scheme.get("short_name") or scheme.get("scheme_name", "")
        keywords_map[key] = _build_scheme_keywords(scheme)

    logger.info("scheme_engine loaded %d schemes", len(raw))
    return raw, keywords_map


# ── Module-level singletons ──────────────────────────────────────────────────
try:
    _SCHEMES: List[dict] = []
    _KEYWORDS: Dict[str, List[str]] = {}
    _SCHEMES, _KEYWORDS = _load()
except Exception as _e:
    logger.error("scheme_engine load failed: %s", _e)


# ── Scheme Detection ─────────────────────────────────────────────────────────
def detect_scheme(query: str) -> Optional[str]:
    """
    Returns the short_name of the best-matching scheme, or None.
    Score = count of keyword tokens that appear in the query.
    """
    if not query or not _SCHEMES:
        return None

    q_tokens = set(_tokenize(query))
    if not q_tokens:
        return None

    best_name: Optional[str] = None
    best_score = 0

    for short_name, kws in _KEYWORDS.items():
        score = sum(1 for k in kws if k in q_tokens)
        if score > best_score:
            best_score = score
            best_name = short_name

    return best_name if best_score > 0 else None


def _get_scheme_data(short_name: str) -> Optional[dict]:
    for s in _SCHEMES:
        key = s.get("short_name") or s.get("scheme_name", "")
        if key == short_name:
            return s
    return None


# ── Topic Detection ───────────────────────────────────────────────────────────
def detect_topic(query: str) -> str:
    """Returns: 'eligibility' | 'documents' | 'apply' | 'summary'"""
    q = query.lower()
    if any(k in q for k in _ELIGIBILITY_KW):
        return "eligibility"
    if any(k in q for k in _DOCUMENTS_KW):
        return "documents"
    if any(k in q for k in _APPLY_KW):
        return "apply"
    return "summary"


# ── Response Builder ──────────────────────────────────────────────────────────
def _format_value(value: object, language: str) -> str:
    lang = "hi" if (language or "").strip().lower() == "hi" else "en"
    if isinstance(value, list):
        parts = [str(v).strip() for v in value if str(v).strip()]
        if not parts:
            return ""
        sep = "। " if lang == "hi" else ". "
        text = sep.join(parts)
        if lang == "hi" and not text.endswith("।"):
            text += "।"
        if lang == "en" and not text.endswith("."):
            text += "."
        return text
    return str(value or "").strip()


def build_response(short_name: str, topic: str, language: str) -> dict:
    """
    Returns a dict: {confirmation, explanation, next_step, confidence}
    """
    lang = "hi" if (language or "").strip().lower() == "hi" else "en"
    data = _get_scheme_data(short_name)

    if not data:
        if lang == "hi":
            return {
                "confirmation": "आप किस स्कीम के बारे में जानना चाहते हैं?",
                "explanation": "",
                "next_step": "",
                "confidence": 0.0,
            }
        return {
            "confirmation": "Which scheme would you like to know about?",
            "explanation": "",
            "next_step": "",
            "confidence": 0.0,
        }

    name = data.get("scheme_name", short_name)
    name_hi = str(
        data.get("scheme_name_hi")
        or data.get("name_hi")
        or data.get("short_name_hi")
        or ""
    ).strip()
    
    # Topic-specific fields
    field_map = {
        "eligibility": ("eligibility_hi", "eligibility_en", None, None),
        "documents":   ("documents_required_hi", "documents_required_en", "how_to_apply_hi", "how_to_apply_en"),
        "apply":       ("how_to_apply_hi", "how_to_apply_en", None, None),
        "summary":     ("description_hi", "description_en", None, None),
    }
    hi_field, en_field, hi_fallback, en_fallback = field_map.get(
        topic, ("description_hi", "description_en", None, None)
    )

    if lang == "hi":
        content = _format_value(data.get(hi_field, ""), language)
        if not content and hi_fallback:
            content = _format_value(data.get(hi_fallback, ""), language)
        if not content:
            content = _format_value(data.get("description_hi", ""), language)
        # Truncate content to ~300 chars for speed
        if len(content) > 300:
            content = content[:300].rsplit(' ', 1)[0] + "..."
            
        if topic == "summary":
            confirmation = f"{name_hi} के बारे में जानकारी: " if name_hi else "योजना के बारे में जानकारी: "
            explanation = f"{content} क्या आप पात्रता, दस्तावेज़ या आवेदन प्रक्रिया जानना चाहेंगे?"
        else:
            # ONLY return topic info, do not repeat summary
            topic_label = {
                "eligibility": "पात्रता जानकारी:",
                "documents": "दस्तावेज़ जानकारी:",
                "apply": "आवेदन प्रक्रिया:",
            }.get(topic, "जानकारी:")
            confirmation = topic_label
            explanation = content
            
        return {
            "confirmation": confirmation,
            "explanation": explanation,
            "next_step": "",
            "confidence": 0.9,
        }
    else:
        content = _format_value(data.get(en_field, ""), language)
        if not content and en_fallback:
            content = _format_value(data.get(en_fallback, ""), language)
        if not content:
            content = _format_value(data.get("description_en", ""), language)
        # Truncate content to ~300 chars for speed
        if len(content) > 300:
            content = content[:300].rsplit(' ', 1)[0] + "..."
            
        if topic == "summary":
            confirmation = f"Information about {name}: "
            explanation = f"{content} Would you like to know eligibility, documents, or how to apply?"
        else:
            # ONLY return topic info, do not repeat summary
            topic_label = {
                "eligibility": "Eligibility details:",
                "documents": "Documents needed:",
                "apply": "How to apply:",
            }.get(topic, "Details:")
            confirmation = topic_label
            explanation = content
            
        return {
            "confirmation": confirmation,
            "explanation": explanation,
            "next_step": "",
            "confidence": 0.9,
        }


# ── Main Entry Point ──────────────────────────────────────────────────────────
def get_scheme_response(
    query: str,
    language: str,
    last_scheme: Optional[str] = None,
) -> Tuple[dict, str, float]:
    """
    Primary entry: returns (response_dict, matched_short_name, confidence).
    Falls back to last_scheme if no scheme detected in query.
    """
    topic = detect_topic(query)
    scheme = detect_scheme(query)

    # Follow-up: reuse last scheme if current query is vague
    words = query.strip().split()
    if not scheme and last_scheme and (len(words) < 6 or topic != "summary"):
        scheme = last_scheme
        logger.info("scheme_context_reuse scheme=%r", scheme)

    if not scheme:
        lang = "hi" if (language or "").strip().lower() == "hi" else "en"
        fallback = {
            "confirmation": "आप किस स्कीम के बारे में जानना चाहते हैं?" if lang == "hi"
                            else "Which scheme would you like to know about?",
            "explanation": "",
            "next_step": "",
            "confidence": 0.0,
        }
        return fallback, "", 0.0

    response = build_response(scheme, topic, language)
    return response, scheme, float(response.get("confidence", 0.9))
