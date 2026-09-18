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

import sys

import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://localhost:8000"


def api(method: str, path: str, **kwargs):
    r = requests.request(method, f"{BASE}{path}", timeout=90, **kwargs)
    r.raise_for_status()
    return r.json()


def main():
    active = api("GET", "/api/lecturer/lectures/active")
    if active["lecture"]:
        lecture = active["lecture"]
        print(f"Reusing already-active lecture #{lecture['id']} ({lecture['display_label']})")
    else:
        lecture = api("POST", "/api/lecturer/lectures", json={"label": "Simulated lecture"})
        print(f"Created lecture #{lecture['id']} ({lecture['display_label']})")

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
    for name, code in submissions:
        print(f"Submitting as {name}...")
        res = api(
            "POST",
            "/api/submit",
            json={"student_name": name, "question_id": q1["id"], "source_code": code},
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
                "student_name": "Alice",
                "question_id": started["id"],
                "source_code": "a, b = map(int, input().split()); print(a + b)",
            },
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
