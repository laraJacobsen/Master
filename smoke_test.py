"""
Structural smoke test for the prototype backend.

Mocks both external dependencies (Judge0's HTTP API and Ollama's HTTP API)
so this runs anywhere without a live Judge0 instance or a running Ollama --
it proves the FastAPI app, SQLite store, and request/response plumbing are
wired correctly end to end. It does NOT prove Judge0 execution or the local
model's actual judgment quality; that needs a real run against a live
Judge0 (see README.md) and a real Ollama instance.

Run: python3 smoke_test.py   (from /root/prototype)
"""

import base64
import json as json_lib  # `fake_post` below has its own `json` parameter (the request body)
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

os.environ["PROTOTYPE_DB_PATH"] = "/tmp/smoke_prototype.db"
if os.path.exists(os.environ["PROTOTYPE_DB_PATH"]):
    os.remove(os.environ["PROTOTYPE_DB_PATH"])


def fake_post(url, params=None, json=None, timeout=None):
    """Stands in for requests.post to either Judge0's /submissions endpoint or
    Ollama's /api/chat endpoint -- ai_feedback.py and judge0_client.py both
    call through the same requests.post, so one fake dispatches on URL.
    Judge0 branch actually evaluates 'sum of space-separated ints' so a
    genuinely correct submission looks correct and a broken one looks broken.
    Ollama branch returns a canned, schema-valid JSON verdict."""
    resp = MagicMock()
    resp.raise_for_status = lambda: None

    if url.endswith("/api/chat"):
        resp.json.return_value = {
            "message": {
                "content": json_lib.dumps(
                    {
                        "verdict": "correct",
                        "error_type": "none",
                        "discussion_point": (
                            "Several students used sum()+split(); worth showing as the "
                            "idiomatic approach."
                        ),
                    }
                )
            }
        }
        return resp

    stdin = base64.b64decode(json["stdin"]).decode()
    try:
        total = sum(int(x) for x in stdin.split())
        stdout_val = str(total)
        status = {"id": 3, "description": "Accepted"}
    except Exception:
        stdout_val = ""
        status = {"id": 6, "description": "Compilation Error"}
    resp.json.return_value = {
        "status": status,
        "stdout": base64.b64encode((stdout_val + "\n").encode()).decode(),
        "stderr": None,
        "compile_output": None,
        "message": None,
        "time": "0.01",
        "memory": 1234,
        "exit_code": 0,
    }
    return resp


def fake_get(url, timeout=None):
    """Stands in for requests.get to Ollama's /api/tags reachability check."""
    resp = MagicMock()
    resp.raise_for_status = lambda: None
    resp.json.return_value = {"models": [{"name": "llama3.2:3b"}]}
    return resp


def main():
    with patch("backend.judge0_client.requests.post", side_effect=fake_post), \
         patch("backend.ai_feedback.requests.get", side_effect=fake_get):

        from fastapi.testclient import TestClient

        from backend.main import app

        # TestClient must be used as a context manager for startup events
        # (store.init_db()) to actually fire.
        with TestClient(app) as client:
            _run_checks(client)

    print("\nALL SMOKE TESTS PASSED")


def _run_checks(client):
        r = client.get("/api/questions")
        assert r.status_code == 200, r.text
        qs = r.json()
        assert any(q["id"] == "sum-ints" for q in qs), qs
        print("GET /api/questions            OK ->", qs)

        r = client.post(
            "/api/submit",
            json={
                "student_name": "Test Student",
                "question_id": "sum-ints",
                "source_code": "print(sum(int(x) for x in input().split()))",
            },
        )
        assert r.status_code == 200, r.text
        data = r.json()
        print("POST /api/submit               OK ->", data)
        assert data["verdict"] == "correct"
        assert data["tests_passed"] == data["tests_total"] == 5

        r = client.get("/api/lecturer/submissions")
        assert r.status_code == 200, r.text
        subs = r.json()
        assert len(subs) == 1
        assert subs[0]["attempt_number"] == 1, subs[0]
        assert subs[0]["exec_verdict"] == "pass", subs[0]
        print("GET /api/lecturer/submissions  OK ->", len(subs), "row(s)")

        r = client.get(f"/api/lecturer/submissions/{data['submission_id']}")
        assert r.status_code == 200, r.text
        print("GET submission detail          OK")

        # Second attempt from the same student+question -- attempt_number increments.
        r = client.post(
            "/api/submit",
            json={
                "student_name": "Test Student",
                "question_id": "sum-ints",
                "source_code": "print(sum(int(x) for x in input().split()))",
            },
        )
        assert r.status_code == 200, r.text
        subs = client.get("/api/lecturer/submissions").json()
        latest = subs[0]
        assert latest["attempt_number"] == 2, subs
        print("attempt_number increments      OK")

        # Rejected before ever reaching Judge0/Claude -- still a stored,
        # 200-status attempt, just tagged with a rejection_reason.
        r = client.post(
            "/api/submit",
            json={"student_name": "Test Student", "question_id": "sum-ints", "source_code": "   "},
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["tests_passed"] == 0 and data["tests_total"] == 5, data
        rejected_row = client.get("/api/lecturer/submissions").json()[0]
        assert rejected_row["exec_verdict"] == "rejected", rejected_row
        assert rejected_row["rejection_reason"] == "whitespace_only", rejected_row
        print("Pre-execution rejection        OK ->", rejected_row["rejection_reason"])

        r = client.get("/api/lecturer/clusters")
        assert r.status_code == 200, r.text
        clusters = r.json()
        pass_cluster = next(c for c in clusters if c["exec_verdict"] == "pass")
        assert pass_cluster["count"] == 2, clusters  # the two correct submissions above
        rejected_cluster = next(c for c in clusters if c["exec_verdict"] == "rejected")
        assert rejected_cluster["count"] == 1, clusters
        print("GET /api/lecturer/clusters     OK ->", clusters)

        r = client.post(
            "/api/submit",
            json={"student_name": "X", "question_id": "does-not-exist", "source_code": "pass"},
        )
        assert r.status_code == 404, r.text
        print("Unknown question -> 404        OK")

        r = client.get("/student.html")
        assert r.status_code == 200 and "Submit" in r.text, r.status_code
        print("Static frontend (student.html) OK")

        r = client.get("/lecturer.html")
        assert r.status_code == 200 and "Discussion" in r.text, r.status_code
        print("Static frontend (lecturer.html)OK")


if __name__ == "__main__":
    main()
