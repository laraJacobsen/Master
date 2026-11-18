#!/usr/bin/env python3
"""Dev-only helper: drives a running backend end to end over HTTP -- the same
steps as the manual walkthrough (new lecture -> author/start a question -> a
few real submissions -> next task -> end session) -- so the result can just
be looked at in the browser instead of typed in by hand.

Unlike smoke_test.py, this hits a REAL running server with REAL Judge0 +
Ollama calls, not mocks -- so each submission takes a few seconds, and this
leaves real rows in whatever database that server is using (fine to archive
afterward from the home dashboard if it's your real dev DB).

Run: python3 simulate_lecture.py [base_url]   (default http://localhost:8000)
"""

import os
import sys

import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"


# The lecturer password, if the server has one (see backend/auth.py).
LECTURER_HEADERS = {"X-Lecturer-Token": os.environ["LECTURER_PASSWORD"]} if os.environ.get("LECTURER_PASSWORD") else {}


def api(method: str, path: str, **kwargs):
    kwargs["headers"] = {**LECTURER_HEADERS, **kwargs.get("headers", {})}
    r = requests.request(method, f"{BASE}{path}", timeout=90, **kwargs)
    r.raise_for_status()
    return r.json()


def join(lecture: dict, name: str) -> dict:
    """Joins as `name` and returns the headers that student's calls send. A
    reused lecture may already have the name from an earlier run (409): then
    "Alice 2", "Alice 3", ..."""
    for n in range(1, 20):
        attempt = name if n == 1 else f"{name} {n}"
        r = requests.post(
            f"{BASE}/api/lecture/join", json={"code": lecture["join_code"], "student_name": attempt}, timeout=30
        )
        if r.status_code != 409:
            r.raise_for_status()
            return {"X-Student-Token": r.json()["token"]}
    raise RuntimeError(f"Couldn't join as {name!r}: every variant of the name is taken")


def main():
    active = api("GET", "/api/lecturer/lectures/active")
    if active["lecture"]:
        lecture = active["lecture"]
        print(f"Reusing already-active lecture #{lecture['id']} ({lecture['display_label']})")
    else:
        lecture = api("POST", "/api/lecturer/lectures", json={"label": "Simulated lecture"})
        print(f"Created lecture #{lecture['id']} ({lecture['display_label']})")

    if not lecture.get("lobby_opened_at"):
        # Starting a question now requires the lobby to be open (see the
        # lobby-scoping-decision) -- skip straight past the "students
        # trickle in" wait, since this script is about exercising the rest
        # of the flow quickly, not the lobby itself.
        lecture = api("POST", f"/api/lecturer/lectures/{lecture['id']}/open_lobby")
        print(f"Opened lobby -- join code {lecture['join_code']}")

    # --- Task 1 ---
    q1 = api(
        "POST",
        "/api/lecturer/questions",
        json={
            "title": "Double It",
            "prompt": "Read one integer and print double it.",
            "language": "python",
            "test_cases": [
                {"stdin": "3\n", "expected_stdout": "6"},
                {"stdin": "10\n", "expected_stdout": "20"},
            ],
            "reference_solution": "print(int(input()) * 2)",
            "expected_students": 3,
            "duration_seconds": 120,
        },
    )
    print(f"Created question {q1['id']!r}")
    v = api("POST", f"/api/lecturer/questions/{q1['id']}/validate")
    assert v["validated"], v
    q1 = api("POST", f"/api/lecturer/questions/{q1['id']}/start")
    print(f"Started {q1['id']!r} -- live now")

    # A few real submissions, including a bug two students share (exercises
    # real Ollama sub-clustering/discussion points) and a NameError.
    submissions = [
        ("Alice", "print(int(input()) * 2)"),  # correct
        ("Bob", "print(int(input()) + 2)"),  # wrong, shared bug
        ("Carol", "print(int(input()) + 2)"),  # wrong, shared bug
        ("Dave", "print(int(inpt()) * 2)"),  # NameError
    ]
    students = {name: join(lecture, name) for name, _ in submissions}
    for name, code in submissions:
        print(f"Submitting as {name}...")
        res = api(
            "POST",
            "/api/submit",
            json={"question_id": q1["id"], "source_code": code},
            headers=students[name],
        )
        print(f"  -> {res['verdict']} ({res['tests_passed']}/{res['tests_total']})")

    # --- Task 2, so "Next task" has something to advance to ---
    q2 = api(
        "POST",
        "/api/lecturer/questions",
        json={
            "title": "Sum Two",
            "prompt": "Read two integers on one line and print their sum.",
            "language": "python",
            "test_cases": [{"stdin": "3 4\n", "expected_stdout": "7"}],
            "reference_solution": "a, b = map(int, input().split()); print(a + b)",
        },
    )
    v = api("POST", f"/api/lecturer/questions/{q2['id']}/validate")
    assert v["validated"], v
    print(f"Prepared next draft question {q2['id']!r} (not started yet)")

    next_res = api("POST", "/api/lecturer/lecture/next", json={"current_question_id": q1["id"]})
    started = next_res["started"]
    print(f"Next task -> {started['id'] if started else 'nothing left'}")

    if started:
        api(
            "POST",
            "/api/submit",
            json={
                "question_id": started["id"],
                "source_code": "a, b = map(int, input().split()); print(a + b)",
            },
            headers=students["Alice"],
        )
        print("Submitted one correct answer for task 2")

    finish = api("POST", "/api/lecturer/lecture/finish", json={"current_question_id": started["id"] if started else None})
    print(f"Finished lecture -> lecture_id={finish['lecture_id']}")

    print()
    print("Open in the browser:")
    print(f"  Home dashboard:  {BASE}/")
    print(f"  Summary view:    {BASE}/lecturer.html?lecture_id={finish['lecture_id']}")


if __name__ == "__main__":
    main()
