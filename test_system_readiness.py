"""
Auto-test: 10 queries + follow-up conversation testing.
Run from project root: python test_system_readiness.py
"""
import os
import sys
import time

# Load env first
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
from dotenv import load_dotenv
load_dotenv("backend/.env")

import json
from backend.services.pipeline_service import process_user_input

PASS = "\033[92m✓ PASS\033[0m"
FAIL = "\033[91m✗ FAIL\033[0m"
WARN = "\033[93m⚠ WARN\033[0m"

results = []

def run_query(label, user_id, session_id, lang, query, expect_scheme_substring=None, expect_not_fallback=True):
    start = time.time()
    try:
        res = process_user_input(user_id, session_id, lang, query)
        elapsed = time.time() - start

        rt = res.get("response_text", {})
        confirmation = rt.get("confirmation", "") if isinstance(rt, dict) else str(rt)
        fallback = res.get("fallback_used", True)
        confidence = res.get("confidence", 0.0)
        session = res.get("session_id", "")
        audio = res.get("audio_base64", "")

        scheme_ok = True
        if expect_scheme_substring:
            scheme_ok = expect_scheme_substring.lower() in confirmation.lower()

        fallback_ok = (not fallback) if expect_not_fallback else True
        status = PASS if (scheme_ok and fallback_ok) else FAIL

        print(f"\n{'='*60}")
        print(f"[{label}]  lang={lang}  elapsed={elapsed:.1f}s  confidence={confidence:.2f}")
        print(f"Query   : {query}")
        print(f"Response: {confirmation[:120]}")
        print(f"Fallback: {fallback}  |  Session: {session}")
        print(f"Audio   : {'YES (' + str(len(audio)) + ' chars)' if audio else 'NO'}")
        print(f"Status  : {status}")
        if not scheme_ok:
            print(f"         Expected scheme containing: '{expect_scheme_substring}'")

        results.append({
            "label": label, "pass": scheme_ok and fallback_ok,
            "elapsed": elapsed, "confidence": confidence, "fallback": fallback
        })
        return res.get("session_id", session_id), res
    except Exception as e:
        elapsed = time.time() - start
        print(f"\n{'='*60}")
        print(f"[{label}] EXCEPTION after {elapsed:.1f}s: {e}")
        results.append({"label": label, "pass": False, "elapsed": elapsed, "confidence": 0, "fallback": True})
        return session_id, {}

# ── TEST GROUP 1: Fresh queries ──────────────────────────────────────────
print("\n\n🔷 GROUP 1: Core scheme queries")
uid = "testuser_auto"

sid, _ = run_query("1. PM-KISAN Hindi",    uid, None, "hi", "पीएम किसान योजना के बारे में बताएं", "KISAN")
sid, _ = run_query("2. PM-KISAN English",  uid, None, "en", "What is PM Kisan scheme?", "KISAN")
sid, _ = run_query("3. Ayushman Bharat",   uid, None, "hi", "आयुष्मान भारत योजना क्या है", "Ayushman")
sid, _ = run_query("4. Ujjwala Yojana",    uid, None, "en", "Tell me about Pradhan Mantri Ujjwala Yojana", "Ujjwala")
sid, _ = run_query("5. Kisan Credit Card", uid, None, "hi", "किसान क्रेडिट कार्ड की जानकारी दें", "Credit Card")

# ── TEST GROUP 2: Follow-up context chain ────────────────────────────────
print("\n\n🔷 GROUP 2: Follow-up context chain (PM-KISAN → patarta → documents)")
session2, _ = run_query("6. PM-KISAN base",    uid, None,     "hi", "पीएम किसान योजना के बारे में बताएं", "KISAN")
session2, _ = run_query("7. patarta follow-up", uid, session2, "hi", "patarta kya hai",                       None, False)
session2, _ = run_query("8. documents follow-up",uid, session2,"hi", "documents kya chahiye",                 None, False)
session2, _ = run_query("9. apply follow-up",  uid, session2, "hi", "kaise apply kare",                      None, False)

# ── TEST GROUP 3: Edge cases ──────────────────────────────────────────────
print("\n\n🔷 GROUP 3: Edge cases")
run_query("10. Empty-ish query", uid, None, "hi", "haan", None, False)

# ── SUMMARY ───────────────────────────────────────────────────────────────
print("\n\n" + "="*60)
print("📊 READINESS REPORT")
print("="*60)
passed = sum(1 for r in results if r["pass"])
total = len(results)
avg_time = sum(r["elapsed"] for r in results) / total
avg_conf = sum(r["confidence"] for r in results) / total
fallbacks = sum(1 for r in results if r["fallback"])

score = int((passed / total) * 100)
print(f"Tests passed : {passed}/{total}")
print(f"Avg latency  : {avg_time:.1f}s")
print(f"Avg confidence: {avg_conf:.2f}")
print(f"Fallback used: {fallbacks}/{total}")
print(f"\n🏆 READINESS SCORE: {score}%")

for r in results:
    icon = "✓" if r["pass"] else "✗"
    print(f"  {icon} {r['label']:<30} {r['elapsed']:.1f}s  conf={r['confidence']:.2f}  fallback={r['fallback']}")

if score >= 80:
    print("\n✅ System is DEMO READY")
elif score >= 60:
    print("\n⚠️  System needs minor fixes before demo")
else:
    print("\n❌ System has critical issues — fix before demo")
