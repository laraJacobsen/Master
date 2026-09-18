"""
Structural smoke test for the prototype backend.

Mocks Judge0's HTTP API (always) and Ollama's HTTP API (only reached from
backend/aggregation.py, for describing a shared code pattern inside a wrong_answer
sub-cluster -- see that module's docstring for the pipeline and why this is a
different, narrower risk than the lecturer discussion-point call this project
removed twice before). Both Judge0 and Ollama are reached through the same
`requests` module object regardless of which file imports it (patch() on either
module's `requests.post` patches the single shared module in sys.modules), so
fake_post below MUST dispatch on URL rather than assuming every call is a Judge0
call -- an earlier version of this file didn't do that, and Ollama calls were
silently swallowed by the Judge0 mock's `json["source_code"]` lookup raising and
being caught by the retry loop, masking a real bug as a passing test.

Proves the FastAPI app, SQLite store, and request/response plumbing are wired
correctly end to end, including that the sub-clustering step actually separates
differently-shaped bugs and that the narrowed Ollama call it uses stays anonymized.
Does NOT prove Judge0 execution or real Ollama's actual output quality; those need
a live Judge0 (see README.md) and a live Ollama.

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
DOUBLE_MARKER = "int(input()) * 2"  # substring fake_post dispatches on
DOUBLE_MARKER_CODE = f"print({DOUBLE_MARKER})"  # reference solution for the question-setup flow test below

# Two structurally different wrong_answer bugs on the same exercise -- real code, not bare
# marker strings, so _canonicalize()/TF-IDF has something genuine to tell apart. Each
# marker is inside a comment, which _canonicalize() strips entirely, so it can't leak into
# the clustering signal or make the two bugs look artificially similar/different.
BUG_A_CODE = "nums = input().split()\nprint(sum(int(n) for n in nums) + 1)  # bug_a_add_one"
# Deliberately "count instead of sum" -- guaranteed wrong on every test case (unlike an
# earlier draft using product, which coincidentally equals the sum for a couple of the
# real test cases, e.g. the single-number one, giving false partial credit).
BUG_B_CODE = "nums = input().split()\nprint(len(nums))  # bug_b_count_instead_of_sum"

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
    """Stands in for requests.post to either Judge0's /submissions endpoint or Ollama's
    /api/chat endpoint -- see module docstring for why one fake must dispatch on URL."""
    resp = MagicMock()
    resp.raise_for_status = lambda: None

    if url.endswith("/api/chat"):
        ollama_chat_calls.append(json)
        resp.json.return_value = {
            "message": {
                "content": json_lib.dumps(
                    {"discussion_point": "All snippets share the same overall structure."}
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
    if DOUBLE_MARKER in source:
        status = {"id": 3, "description": "Accepted"}
        resp.json.return_value = {
            "status": status,
            "stdout": base64.b64encode((str(int(stdin.strip()) * 2) + "\n").encode()).decode(),
            "stderr": None,
            "compile_output": None,
            "message": None,
            "time": "0.01",
            "memory": 1234,
            "exit_code": 0,
        }
        return resp

    nums = [int(x) for x in stdin.split()]
    if "bug_a_add_one" in source:
        stdout_val = str(sum(nums) + 1)  # deliberately off by one
    elif "bug_b_count_instead_of_sum" in source:
        stdout_val = str(len(nums))  # deliberately the wrong operation entirely
    elif "bug_c_subtract_one" in source:
        stdout_val = str(sum(nums) - 1)  # deliberately off by one, the other direction
    else:
        stdout_val = str(sum(nums))

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

        # A fresh checkout's seeded lecture must already have a join code --
        # otherwise the student page's join screen (see student/App.tsx)
        # would have nothing valid to accept until a lecturer clicks "New
        # lecture" once, breaking the "just clone and run" out-of-box flow.
        r = client.get("/api/lecturer/lectures/active")
        assert r.status_code == 200, r.text
        seed_lecture = r.json()["lecture"]
        assert seed_lecture and seed_lecture["join_code"], seed_lecture
        r = client.post("/api/lecture/join", json={"code": seed_lecture["join_code"]})
        assert r.status_code == 200, r.text
        print("Seeded lecture already has a working join code   OK ->", seed_lecture["join_code"])

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
        # count must stay at 2 (not 3), and its discussion point must be exactly the
        # curated feedback.py text -- no count prefix, no model-written lead-in, just
        # the one deterministic, actionable line. NameError isn't sub-clustered (that's
        # wrong_answer-only), so this exercises the plain deterministic path.
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
        from backend import hints
        expected = hints.discussion_point_for_cluster("runtime_error", "NameError", 2)
        assert name_error_cluster["discussion_point"] == expected, clusters
        assert "students hit this" not in expected, "count prefix should be gone"
        print("Cluster dedup by student, curated text          OK ->", name_error_cluster)

        # Two structurally different wrong_answer bugs, two students each. This is the
        # actual point of sub-clustering: they must NOT be merged into one generic
        # wrong_answer bucket -- each shape gets its own cluster entry, each independently
        # clearing the discussion threshold and getting the mocked Ollama pattern
        # description (cached per sub-cluster, not per submission).
        for student in ("Carol", "Dave"):
            r = client.post(
                "/api/submit",
                json={"student_name": student, "question_id": "sum-ints", "source_code": BUG_A_CODE},
            )
            assert r.status_code == 200 and r.json()["verdict"] == "incorrect", r.json()
        for student in ("Kasper", "Vilde"):
            r = client.post(
                "/api/submit",
                json={"student_name": student, "question_id": "sum-ints", "source_code": BUG_B_CODE},
            )
            assert r.status_code == 200 and r.json()["verdict"] == "incorrect", r.json()

        clusters = client.get("/api/lecturer/clusters").json()
        wrong_answer_clusters = [c for c in clusters if c["exec_verdict"] == "wrong_answer"]
        assert len(wrong_answer_clusters) == 2, (
            f"expected the two different bugs to land in separate sub-clusters, got {wrong_answer_clusters}"
        )
        for c in wrong_answer_clusters:
            assert c["count"] == 2, clusters
            assert c["discussion_point"] == "All snippets share the same overall structure.", clusters
        print("wrong_answer sub-clustering separates two bug shapes  OK ->", wrong_answer_clusters)

        # The sub-cluster Ollama call must only ever see canonicalized snippets -- never
        # student names, never the real identifiers, never the marker comments (which
        # _canonicalize() strips as comments). Exactly one call per sub-cluster (cached).
        assert len(ollama_chat_calls) == 2, ollama_chat_calls
        sent = json_lib.dumps(ollama_chat_calls)
        for leaked in ("Carol", "Dave", "Kasper", "Vilde", "bug_a_add_one", "bug_b_count_instead_of_sum", "nums"):
            assert leaked not in sent, (leaked, sent)
        assert "VAR1" in sent, sent
        print("Sub-cluster Ollama call carries no names/code    OK")

        # Fallback path, tested directly against _subcluster_discussion_point() rather
        # than through another full HTTP round trip: whether a third real submission
        # would land in its own sub-cluster or get folded into an existing one depends
        # on the clustering algorithm's behavior on that specific corpus (a known rough
        # edge of this MVP -- see module docstring), which isn't what this check is
        # about. This isolates the one thing that matters here: when Ollama is
        # unreachable, a sub-cluster must fall back to the generic curated line, not
        # error or go silent.
        from backend import aggregation
        _ollama_state["available"] = False
        synthetic_group = [
            {"id": 9001, "student_name": "Erik", "source_code": "print(1)"},
            {"id": 9002, "student_name": "Frida", "source_code": "print(2)"},
        ]
        fallback_point = aggregation._subcluster_discussion_point(synthetic_group, student_count=2)
        assert fallback_point == hints.discussion_point_for_cluster("wrong_answer", None, 2), fallback_point
        assert len(ollama_chat_calls) == 2, "Ollama should not have been called while unreachable"
        print("wrong_answer sub-cluster falls back when Ollama down  OK ->", fallback_point)

        r = client.post(
            "/api/submit",
            json={"student_name": "X", "question_id": "does-not-exist", "source_code": "pass"},
        )
        assert r.status_code == 404, r.text
        print("Unknown question -> 404        OK")

        # These now serve the built React/TS bundle's HTML shell (see
        # frontend/README.md) -- content like "Submit" is rendered client-side,
        # not present in the served HTML, so this only checks the right shell
        # (via its <title>) and a bundled JS entrypoint come back.
        r = client.get("/student.html")
        assert r.status_code == 200 and "Student" in r.text and 'id="root"' in r.text, r.status_code
        print("Static frontend (student.html) OK")

        r = client.get("/lecturer.html")
        assert r.status_code == 200 and "Lecturer" in r.text and 'id="root"' in r.text, r.status_code
        print("Static frontend (lecturer.html)OK")

        r = client.get("/")
        assert r.status_code == 200 and 'id="root"' in r.text, r.status_code
        print("Static frontend (index.html, site root) OK")

        _run_question_setup_checks(client)
        _run_lecture_dashboard_checks(client)


def _run_question_setup_checks(client):
    """Landing-page (question setup) flow: draft -> validate -> start -> live,
    plus the per-question config knobs (line_limit, extra_packages) and the
    lock-on-start rule -- see landing-page-scoping-decision.md."""
    r = client.post(
        "/api/lecturer/questions",
        json={
            "title": "Double It",
            "prompt": "Read one integer and print double it.",
            "language": "python",
            "test_cases": [
                {"stdin": "3\n", "expected_stdout": "6"},
                {"stdin": "10\n", "expected_stdout": "20"},
            ],
            "line_limit": 3,
            "extra_packages": [],
            "expected_students": 3,
        },
    )
    assert r.status_code == 200, r.text
    question = r.json()
    qid = question["id"]
    assert question["status"] == "draft" and question["validated"] is False, question
    print("POST /api/lecturer/questions   OK ->", qid)

    # Not yet live -- must not show up in the student-facing list, and a draft
    # question must reject submissions rather than silently grading them.
    assert qid not in [q["id"] for q in client.get("/api/questions").json()]
    r = client.post("/api/submit", json={"student_name": "X", "question_id": qid, "source_code": "pass"})
    assert r.status_code == 409, r.text
    print("Draft question hidden + rejects submissions   OK")

    # Validating without a reference solution is refused outright.
    r = client.post(f"/api/lecturer/questions/{qid}/validate")
    assert r.status_code == 400, r.text
    # Starting before validation is refused too.
    r = client.post(f"/api/lecturer/questions/{qid}/start")
    assert r.status_code == 400, r.text
    print("Validate/start blocked before a reference solution exists   OK")

    r = client.put(f"/api/lecturer/questions/{qid}", json={"reference_solution": DOUBLE_MARKER_CODE})
    assert r.status_code == 200, r.text
    assert r.json()["validated"] is False, r.json()  # editing config resets validation

    r = client.post(f"/api/lecturer/questions/{qid}/validate")
    assert r.status_code == 200, r.text
    assert r.json()["validated"] is True, r.json()
    print("Validation preview against reference solution   OK ->", r.json()["validated"])

    r = client.post(f"/api/lecturer/questions/{qid}/start")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "live", r.json()
    print("POST .../start -> live   OK")

    # A live question is locked: no further config edits.
    r = client.put(f"/api/lecturer/questions/{qid}", json={"title": "Renamed"})
    assert r.status_code == 409, r.text
    print("Live question rejects further edits   OK")

    assert qid in [q["id"] for q in client.get("/api/questions").json()]

    r = client.post(
        "/api/submit", json={"student_name": "Grace", "question_id": qid, "source_code": DOUBLE_MARKER_CODE}
    )
    assert r.status_code == 200 and r.json()["verdict"] == "correct", r.text
    print("Submit against a newly-started question   OK")

    # line_limit=3 above: a 4-line submission is rejected before Judge0 ever
    # sees it, tagged with the specific reason so it's distinguishable from a
    # genuine wrong answer.
    r = client.post(
        "/api/submit",
        json={
            "student_name": "Grace",
            "question_id": qid,
            "source_code": "a = 1\nb = 2\nc = 3\nprint(a + b + c)",
        },
    )
    assert r.status_code == 200, r.text
    too_long_row = client.get(f"/api/lecturer/submissions?question_id={qid}").json()[0]
    assert too_long_row["rejection_reason"] == "too_long", too_long_row
    print("Per-question line_limit enforced   OK")

    # Default config is stdlib-only -- an import outside it is rejected the
    # same defensive-before-Judge0 way, distinct from a runtime ImportError.
    r = client.post(
        "/api/submit",
        json={"student_name": "Grace", "question_id": qid, "source_code": "import numpy\nprint(1)"},
    )
    assert r.status_code == 200, r.text
    pkg_row = client.get(f"/api/lecturer/submissions?question_id={qid}").json()[0]
    assert pkg_row["rejection_reason"] == "disallowed_package", pkg_row
    print("Package allow-list enforced   OK")

    # Live submission-progress counter (live-submission-progress-scoping-decision.md):
    # Grace's three submissions above (correct + two rejections) count as one
    # distinct student, not three.
    r = client.get(f"/api/lecturer/questions/{qid}/progress")
    assert r.status_code == 200, r.text
    progress = r.json()
    assert progress == {"submitted": 1, "expected": 3, "not_submitted": 2}, progress
    print("Progress counter dedups by student   OK ->", progress)

    r = client.post(
        "/api/submit", json={"student_name": "Henry", "question_id": qid, "source_code": DOUBLE_MARKER_CODE}
    )
    assert r.status_code == 200, r.text
    progress = client.get(f"/api/lecturer/questions/{qid}/progress").json()
    assert progress == {"submitted": 2, "expected": 3, "not_submitted": 1}, progress
    print("Progress counter updates on a new student   OK ->", progress)

    # sum-ints was seeded with no expected_students -- expected/not_submitted
    # must be None (not 0, which would misleadingly read as "everyone's in").
    progress = client.get("/api/lecturer/questions/sum-ints/progress").json()
    assert progress["expected"] is None and progress["not_submitted"] is None, progress
    print("Progress counter with no expected_students set   OK ->", progress)


def _run_lecture_dashboard_checks(client):
    """Home-dashboard flow: the seeded question's lecture is already active,
    so a second "New lecture" must be refused, "resume" info must be
    available, ending it must generalize the summary view to lecture_id, and
    archive/unarchive must hide/restore history without losing data."""
    r = client.get("/api/lecturer/lectures/active")
    assert r.status_code == 200, r.text
    active = r.json()
    assert active["lecture"] is not None, active
    seeded_lecture_id = active["lecture"]["id"]
    assert active["live_question_id"] is not None, active
    print("GET /api/lecturer/lectures/active     OK ->", active)

    # One active lecture already -- a second "New lecture" is refused.
    r = client.post("/api/lecturer/lectures", json={"label": None})
    assert r.status_code == 409, r.text
    print("POST /api/lecturer/lectures refused while one is active   OK")

    r = client.get("/api/lecturer/lectures")
    assert r.status_code == 200, r.text
    history = r.json()
    seeded_row = next(lec for lec in history if lec["id"] == seeded_lecture_id)
    assert seeded_row["task_count"] == 2, seeded_row  # sum-ints + double-it
    assert seeded_row["submitted_total"] > 0, seeded_row
    assert seeded_row["archived"] is False, seeded_row
    print("GET /api/lecturer/lectures (history)   OK ->", seeded_row)

    # Ending it generalizes straight to a lecture_id -- the home dashboard's
    # history-list link target, not just "whatever's most recent."
    r = client.post("/api/lecturer/lecture/finish", json={"current_question_id": None})
    assert r.status_code == 200, r.text
    finished = r.json()
    assert finished == {"finished": True, "lecture_id": seeded_lecture_id}, finished
    print("POST /api/lecturer/lecture/finish returns lecture_id   OK")

    r = client.get(f"/api/lecturer/lecture/summary?lecture_id={seeded_lecture_id}")
    assert r.status_code == 200, r.text
    summary = r.json()
    assert summary["lecture_id"] == seeded_lecture_id, summary
    assert {t["question_id"] for t in summary["tasks"]} == {"sum-ints", "double-it"}, summary
    print("GET /api/lecturer/lecture/summary?lecture_id=   OK ->", summary["lecture_label"])

    # No lecture active anymore -- "New lecture" now succeeds, and
    # start_question requires exactly this new one.
    r = client.get("/api/lecturer/lectures/active")
    assert r.json() == {"lecture": None, "live_question_id": None}, r.json()

    # Joining with nothing live gets a clear "no lecture" 404, not a
    # generic "wrong code" 403.
    r = client.post("/api/lecture/join", json={"code": "123456"})
    assert r.status_code == 404, r.text
    print("POST /api/lecture/join with no active lecture   OK -> 404")

    r = client.post("/api/lecturer/lectures", json={"label": "Week 3 -- Recursion"})
    assert r.status_code == 200, r.text
    new_lecture = r.json()
    assert new_lecture["display_label"] == "Week 3 -- Recursion", new_lecture
    assert new_lecture["join_code"] and len(new_lecture["join_code"]) == 6, new_lecture
    print("POST /api/lecturer/lectures (New lecture)   OK ->", new_lecture)

    # Kahoot-style join gate: right code lets a student in, wrong code
    # doesn't, and it's case/whitespace-insensitive.
    r = client.post("/api/lecture/join", json={"code": f"  {new_lecture['join_code']}  "})
    assert r.status_code == 200 and r.json()["lecture_id"] == new_lecture["id"], r.text
    r = client.post("/api/lecture/join", json={"code": "000000"})
    assert r.status_code == 403, r.text
    print("POST /api/lecture/join   OK -> correct code accepted, wrong code rejected")

    r = client.post(
        "/api/lecturer/questions",
        json={
            "title": "Sum Again",
            "prompt": "Read space-separated integers and print their sum.",
            "language": "python",
            "test_cases": [{"stdin": "4 5\n", "expected_stdout": "9"}],
            # Matches fake_post's fallback branch (plain sum) -- see module docstring.
            "reference_solution": "print(sum(int(x) for x in input().split()))",
        },
    )
    assert r.status_code == 200, r.text
    qid = r.json()["id"]
    r = client.post(f"/api/lecturer/questions/{qid}/validate")
    assert r.status_code == 200 and r.json()["validated"] is True, r.text
    r = client.post(f"/api/lecturer/questions/{qid}/start")
    assert r.status_code == 200, r.text
    assert r.json()["lecture_id"] == new_lecture["id"], r.json()
    print("New question stamped with the newly active lecture   OK")

    # Archive hides a lecture from the default list without touching its
    # data, and can be undone.
    r = client.post(f"/api/lecturer/lectures/{seeded_lecture_id}/archive")
    assert r.status_code == 200 and r.json()["archived"] is True, r.text
    visible_ids = {lec["id"] for lec in client.get("/api/lecturer/lectures").json()}
    assert seeded_lecture_id not in visible_ids, visible_ids
    all_ids = {lec["id"] for lec in client.get("/api/lecturer/lectures?include_archived=true").json()}
    assert seeded_lecture_id in all_ids, all_ids
    r = client.get(f"/api/lecturer/lecture/summary?lecture_id={seeded_lecture_id}")
    assert r.status_code == 200 and len(r.json()["tasks"]) == 2, r.text  # data untouched
    print("Archive hides from default list, keeps data   OK")

    r = client.post(f"/api/lecturer/lectures/{seeded_lecture_id}/unarchive")
    assert r.status_code == 200 and r.json()["archived"] is False, r.text
    visible_ids = {lec["id"] for lec in client.get("/api/lecturer/lectures").json()}
    assert seeded_lecture_id in visible_ids, visible_ids
    print("Unarchive restores it to the default list   OK")

    r = client.get("/api/lecturer/stats/totals")
    assert r.status_code == 200, r.text
    totals = r.json()
    assert totals["lectures_run"] >= 2, totals
    assert totals["total_submissions"] >= 1, totals
    print("GET /api/lecturer/stats/totals   OK ->", totals)


if __name__ == "__main__":
    main()
