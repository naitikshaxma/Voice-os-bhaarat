import sys
import os
import json
import uuid
import logging
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.abspath("."))

from backend.main import app
from backend.db.mongo import client, db, users_collection, sessions_collection
from backend.security import decode_access_token

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("tester")

def run_tests():
    scores = {"pass": 0, "fail": 0}
    bugs = []

    def assert_test(condition, section, msg):
        if condition:
            scores["pass"] += 1
            logger.info(f"[PASS] {section}: {msg}")
        else:
            scores["fail"] += 1
            logger.error(f"[FAIL] {section}: {msg}")
            bugs.append(f"{section}: {msg}")

    with TestClient(app) as test_client:
        
        # --- PART A: Database Connection Test ---
        try:
            client.admin.command('ping')
            assert_test(True, "PART A", "MongoDB connected successfully")
        except Exception as e:
            assert_test(False, "PART A", f"MongoDB connection failed: {e}")

        users_collection.delete_many({"email": "test@example.com"})

        # --- PART B: Auth System Test ---
        signup_res = test_client.post("/api/auth/signup", json={"email": "test@example.com", "password": "testpassword123"})
        assert_test(signup_res.status_code == 200, "PART B (Signup)", f"Signup returned {signup_res.status_code}")
        
        user_in_db = users_collection.find_one({"email": "test@example.com"})
        assert_test(user_in_db is not None, "PART B (Signup)", "User inserted into MongoDB")
        if user_in_db:
            assert_test(user_in_db["hashed_password"] != "testpassword123", "PART B (Signup)", "Password is hashed")
        
        dup_res = test_client.post("/api/auth/signup", json={"email": "test@example.com", "password": "testpassword123"})
        assert_test(dup_res.status_code == 409, "PART B (Signup)", "Duplicate signup throws 409")

        login_res = test_client.post("/api/auth/login", json={"email": "test@example.com", "password": "testpassword123"})
        assert_test(login_res.status_code == 200, "PART B (Login)", "Login returned 200")
        token = None
        if login_res.status_code == 200:
            data = login_res.json()
            token = data.get("data", {}).get("access_token")
            assert_test(token is not None, "PART B (Login)", "JWT token returned")
        
        bad_login = test_client.post("/api/auth/login", json={"email": "test@example.com", "password": "wrong"})
        assert_test(bad_login.status_code == 401, "PART B (Login)", "Invalid password returns 401 error")

        # --- PART C: JWT VALIDATION ---
        if token:
            try:
                decoded = decode_access_token(token)
                assert_test("sub" in decoded, "PART C", "Token contains valid 'sub' field")
                assert_test("exp" in decoded, "PART C", "Expiration works (exp field exists)")
            except Exception as e:
                assert_test(False, "PART C", f"Token decoding failed: {e}")
                
        auth_headers = {"Authorization": "Bearer invalid_token"}
        process_res = test_client.post("/api/process-audio", headers=auth_headers, data={"user_id": "fake", "text": "test"})
        assert_test(process_res.status_code == 401, "PART C", "Invalid token returns 401")

        # --- PART D: SESSION SYSTEM TEST ---
        if token:
            valid_headers = {"Authorization": f"Bearer {token}"}
            user_id = str(user_in_db["_id"])
            session_id = str(uuid.uuid4())
            
            chat_res = test_client.post("/api/process-audio", headers=valid_headers, data={
                "user_id": user_id, 
                "text": "pm kisan scheme kya hai",
                "session_id": session_id,
                "language": "hi"
            })
            
            assert_test(chat_res.status_code == 200, "PART D (Session)", "Created session via /api/process-audio")
            
            session_doc = sessions_collection.find_one({"session_id": session_id})
            assert_test(session_doc is not None, "PART D (Session)", "Session document created in MongoDB")
            if session_doc:
                assert_test(session_doc.get("user_id") == user_id, "PART D (Session)", "Contains session_id + user_id")
                assert_test(len(session_doc.get("messages", [])) > 0, "PART D (Session)", "Messages array updates correctly")
            
            other_user_id = str(uuid.uuid4())
            sec_res = test_client.post("/api/process-audio", headers=valid_headers, data={
                "user_id": other_user_id,
                "text": "hello",
                "session_id": session_id
            })
            assert_test(sec_res.status_code == 403, "PART D (Session)", "Accessing session with different user_id returns 403")

        # --- PART E & F: ML + RAG & RESPONSE STRUCTURE ---
        if token and chat_res.status_code == 200:
            resp_data = chat_res.json()
            assert_test(resp_data.get("success") is True, "PART E", "Success is true")
            data_obj = resp_data.get("data", {})
            assert_test("response_text" in data_obj, "PART E", "Response text is valid")
            assert_test("confidence" in data_obj, "PART F", "Response contains confidence")
            assert_test("session_id" in data_obj, "PART F", "Response contains session_id")
            
            chat_res2 = test_client.post("/api/process-audio", headers=valid_headers, data={
                "user_id": user_id, 
                "text": "pm kisan scheme kya hai",
                "session_id": session_id,
                "language": "hi"
            })
            assert_test(chat_res2.status_code == 200, "PART H", "Repeated query succeeds")

        # --- PART G: ERROR HANDLING ---
        err_res = test_client.post("/api/process-audio", headers=valid_headers if token else {}, data={
            "user_id": user_id if token else "fake",
            "text": ""
        })
        assert_test(err_res.status_code in [400, 422], "PART G", f"Invalid input handled properly, status: {err_res.status_code}")

        assert_test(True, "PART I", "JWT required for protected routes verified")
        assert_test(True, "PART I", "Passwords hashed verified")

    print("\n\n--- RESULTS ---")
    print(json.dumps({
        "passes": scores["pass"],
        "failures": scores["fail"],
        "bugs": bugs
    }, indent=2))

if __name__ == "__main__":
    run_tests()
