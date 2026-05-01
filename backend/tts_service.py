import base64
import io
from threading import Lock
from gtts import gTTS

_tts_cache = {}
_tts_cache_lock = Lock()
_TTS_CACHE_MAX_ITEMS = 512


def generate_tts(text: str, language: str) -> str:
    clean_text = (text or "").strip()
    if not clean_text:
        return ""

    lang = "hi" if (language or "").strip().lower() == "hi" else "en"
    cache_key = f"{lang}:{clean_text}"

    with _tts_cache_lock:
        cached = _tts_cache.get(cache_key)
    if cached:
        return cached

    tts = gTTS(text=clean_text, lang=lang)

    fp = io.BytesIO()

    tts.write_to_fp(fp)

    encoded = base64.b64encode(fp.getvalue()).decode("utf-8")

    with _tts_cache_lock:
        if len(_tts_cache) >= _TTS_CACHE_MAX_ITEMS:
            # Evict oldest inserted key (dict preserves insertion order).
            oldest_key = next(iter(_tts_cache), None)
            if oldest_key is not None:
                _tts_cache.pop(oldest_key, None)
        _tts_cache[cache_key] = encoded

    return encoded
