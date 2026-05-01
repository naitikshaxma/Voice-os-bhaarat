import os
import time

os.environ.setdefault("PYTHONIOENCODING", "utf-8")
from dotenv import load_dotenv
load_dotenv("backend/.env")

from backend.services.pipeline_service import process_user_input

queries = [
    "PM Kisan kya hai",
    "patarta batao",
    "documents?",
    "apply kaise kare",
    "haan"
]

uid = "final_test_user"
sid = None

print("\n" + "="*50)
print("FINAL DEMO HARDENING TEST")
print("="*50)

for q in queries:
    start = time.time()
    res = process_user_input(uid, sid, "hi", q)
    elapsed = time.time() - start
    
    sid = res.get("session_id", sid)
    text = res.get("response_text", {})
    conf = text.get("confirmation", "") if isinstance(text, dict) else str(text)
    expl = text.get("explanation", "") if isinstance(text, dict) else ""
    
    full_resp = f"{conf} {expl}".strip()
    
    print(f"\nQuery   : {q}")
    print(f"Response: {full_resp[:150]}")
    print(f"Latency : {elapsed:.2f}s  |  Audio: {'YES' if res.get('audio_base64') else 'NO (Skipped/Timeout)'}")
    print(f"Fallback: {res.get('fallback_used')}")
    
print("\nDone.")
