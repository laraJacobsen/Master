"""
Structural smoke test for the prototype backend.

Mocks the two external dependencies still in play: Judge0's HTTP API (always) and
Ollama's HTTP API (only reached from backend/aggregation.py now, for phrasing a
lecturer discussion point -- see its module docstring for why that's the one place
a model was brought back). Proves the FastAPI app, SQLite store, and request/response
plumbing are wired correctly end to end, and that the narrowed Ollama call really is
narrow: fake_post below records every /api/chat request body so _run_checks can
assert no student code or name ever reaches it. Does NOT prove Judge0 execution or
real Ollama's actual output quality; those need a live Judge0 (see README.md) and a
live Ollama.

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

NAME_ERROR_MARKER = "num = inpt().split()"
WRONG_ANSWER_MARKER = "off_by_one_bug"

# Mutable so _run_checks can flip Ollama between "available" (to exercise the live
# phrasing call) and "unreachable" (to exercise the deterministic-template fallback)
# without needing separate patch contexts.
_ollama_state = {"available": True}
ollama_chat_calls = []  # request bodies sent to /api/chat, for the no-leakage assertion


def fake_get(url, timeout=None):
    """Stands in for requests.get to Ollama's /api/tags reachability check."""
    resp = MagicMock()
    resp.raise_for_status = lambda: None
    resp.json.return_value = {
        "models": [{"name": "llama3.2:3b"}] if _ollama_state["available"] else []
    }
    return resp


def fake_post(url, params=None, json=None, timeout=None):
    """Stands in for requests.post to either Judge0's /submissions endpoint or
    Ollama's /api/chat endpoint -- judge0_client.py and aggregation.py both call
    through the same requests.post, so one fake dispatches on URL.

    Judge0 branch actually evaluates 'sum of space-separated ints' so a genuinely
    correct submission looks correct and a broken one looks broken. Source code
    containing NAME_ERROR_MARKER/WRONG_ANSWER_MARKER short-circuits to a canned
    crash/wrong-output result, to exercise those cluster paths without needing a
    real interpreter."""
    resp = MagicMock()
    resp.raise_for_status = lambda: None

    if url.endswith("/api/chat"):
        ollama_chat_calls.append(json)
        resp.json.return_value = {
            "message": {
                "content": json_lib.dumps(
                    {"discussion_point": "Great moment to talk through this one together."}
                )
            }
        }
        return resp

    source = base64.b64decode(json["source_code"]).decode()
    if NAME_ERROR_MARKER in source:
        resp.json.return_value = {
            "status": {"id": 11, "description": "Runtime Error (NZEC)"},
            "stdout": base64.b64encode(b"").decode(),
            "stderr": base64.b64encode(
                b"Traceback (most recent call last):\n"
                b'  File "main.py", line 1, in <module>\n'
                b"NameError: name 'inpt' is not defined"
            ).decode(),
            "compile_output": None,
            "message": None,
            "time": "0.01",
            "memory": 1234,
            "exit_code": 1,
        }
        return resp

    stdin = base64.b64decode(json["stdin"]).decode()
    if WRONG_ANSWER_MARKER in source:
        stdout_val = str(sum(int(x) for x in stdin.split()) + 1)  # deliberately off by one
        status = {"id": 3, "description": "Accepted"}
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


def main():
    with patch("backend.judge0_client.requests.post", side_effect=fake_post), \
         patch("backend.aggregation.requests.post", side_effect=fake_post), \
         patch("backend.aggregation.requests.get", side_effect=fake_get):

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
        # Both correct submissions above are the same student resubmitting -- cluster
        # count is distinct students, not raw submission rows.
        assert pass_cluster["count"] == 1, clusters
        rejected_cluster = next(c for c in clusters if c["exec_verdict"] == "rejected")
        assert rejected_cluster["count"] == 1, clusters
        assert rejected_cluster["discussion_point"] is None, clusters  # below the threshold
        print("GET /api/lecturer/clusters     OK ->", clusters)

        # Same NameError-causing code from two different students, plus one of them
        # resubmitting it a second time unchanged. The cluster's distinct-student
        # count must stay at 2 (not 3), and it should now clear the discussion
        # threshold with one stable talking point -- not three differently-worded
        # ones, one per submission. Ollama is "available" for this one, so the
        # cluster's discussion point should come from the mocked live call.
        for student in ("Alice", "Bob", "Alice"):
            r = client.post(
                "/api/submit",
                json={
                    "student_name": student,
                    "question_id": "sum-ints",
                    "source_code": NAME_ERROR_MARKER,
                },
            )
            assert r.status_code == 200, r.text
            assert r.json()["verdict"] == "error", r.json()

        clusters = client.get("/api/lecturer/clusters").json()
        name_error_cluster = next(
            c for c in clusters if c["exec_verdict"] == "runtime_error" and c["error_type"] == "NameError"
        )
        assert name_error_cluster["count"] == 2, clusters
        # Composed: mocked Ollama lead-in + the curated factual mechanism sentence --
        # the lead-in must never replace the factual content, only precede it.
        assert name_error_cluster["discussion_point"] == (
            "Great moment to talk through this one together. A NameError means Python "
            "doesn't recognize a name that was used -- almost always a typo, or a "
            "variable/function referenced before it was ever defined."
        ), clusters
        print("Cluster dedup by student, Ollama phrasing       OK ->", name_error_cluster)

        # The narrowed Ollama call must never see student code, names, or the specific
        # exception text -- only the category label and count. This is exactly the
        # information leak that mattered: the earlier, wider call was handed the real
        # traceback and still fabricated an unrelated cause, so the fix is to never let
        # it see case-specific detail as well as never let it explain the cause.
        assert len(ollama_chat_calls) == 1, ollama_chat_calls
        sent_prompt = json_lib.dumps(ollama_chat_calls[0])
        for leaked in ("inpt", "Alice", "Bob", NAME_ERROR_MARKER, "Traceback"):
            assert leaked not in sent_prompt, (leaked, sent_prompt)
        assert "NameError" in sent_prompt and "2" in sent_prompt, sent_prompt
        print("Ollama call carries no student code/names       OK")

        # Now the fallback path: Ollama goes unreachable, and a *different* cluster
        # (wrong_answer, from two more distinct students) must fall back to the
        # curated deterministic template rather than erroring or going silent.
        _ollama_state["available"] = False
        for student in ("Carol", "Dave"):
            r = client.post(
                "/api/submit",
                json={
                    "student_name": student,
                    "question_id": "sum-ints",
                    "source_code": WRONG_ANSWER_MARKER,
                },
            )
            assert r.status_code == 200, r.text
            assert r.json()["verdict"] == "incorrect", r.json()

        clusters = client.get("/api/lecturer/clusters").json()
        wrong_answer_cluster = next(c for c in clusters if c["exec_verdict"] == "wrong_answer")
        assert wrong_answer_cluster["count"] == 2, clusters
        assert wrong_answer_cluster["discussion_point"] is not None, clusters
        assert wrong_answer_cluster["discussion_point"].startswith("2 students hit this:"), clusters
        assert len(ollama_chat_calls) == 1, "Ollama should not have been called while unreachable"
        print("Ollama-unreachable falls back to template       OK ->", wrong_answer_cluster)

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
