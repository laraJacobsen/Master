#!/usr/bin/env python3
"""Dev-only load test: one simulated lecture with N students at once, against a
REAL backend + REAL Judge0 -- the "behavior under concurrent submissions" the
README lists as not yet verified.

Starts its own backend (uvicorn, port 8100) on a throwaway SQLite file, so the
dev database is never touched, with no LLM calls (grading never uses one; the
Label call is a separate, lecturer-side concern). Then every student, each in
its own thread, does what student/App.tsx does:

  - joins with the lecture's code
  - polls /api/lecture/status every 2s and heartbeats /api/lecture/activity
    every 10s for the whole run (the cheap background traffic)
  - submits per a plan: correct first time, a shared wrong answer then the fix,
    or a NameError then the fix

while one lecturer thread polls the dashboard endpoints every 3s, as
lecturer/App.tsx does.

--mode burst: every student's first submit lands within ~1s -- the worst case,
  e.g. time's up auto-submitting everyone at once.
--mode spread: first submits spread at random over --spread seconds -- closer to
  a real "type, then submit" lecture.

Reports latency per endpoint (p50/p95/max) and checks correctness: every submit
got the verdict its code deserves, every stored attempt is there, and each
student's attempt numbers are 1..k with no duplicates.

Needs Judge0 running (JUDGE0_BASE_URL, default http://localhost:2358).

--watch: pauses before the run and again after it, so the pages can be looked at in a
  browser: join as a real student first (the code is printed) and submit during the
  burst, then look at the lecturer dashboard with the whole class's data in it.

Run: python load_test.py [--students 40] [--mode burst|spread] [--spread 60] [--watch]
"""

import argparse
import os
import random
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from collections import defaultdict
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent
PORT = 8100
BASE = f"http://127.0.0.1:{PORT}"

STATUS_POLL_S = 2  # POLL_MS in student/App.tsx
HEARTBEAT_S = 10  # HEARTBEAT_MS in student/App.tsx
LECTURER_POLL_S = 3  # lecturer/App.tsx

CORRECT = "nums = input().split()\nprint(sum(int(n) for n in nums))"
WRONG = "nums = input().split()\nprint(sum(int(n) for n in nums) + 1)"
CRASH = "nums = inpt().split()\nprint(sum(int(n) for n in nums))"

# (plan name, weight, [(code, expected verdict), ...])
PLANS = [
    ("correct", 5, [(CORRECT, "correct")]),
    ("wrong_then_fix", 3, [(WRONG, "incorrect"), (CORRECT, "correct")]),
    ("crash_then_fix", 2, [(CRASH, "error"), (CORRECT, "correct")]),
]

_lock = threading.Lock()
latencies = defaultdict(list)  # endpoint name -> [seconds]
failures = []  # (endpoint name, description)
submit_results = []  # (student, expected verdict, actual verdict or None)
stop = threading.Event()


def call(name, method, path, **kwargs):
    """One timed request. Records latency on any response, a failure on a
    non-2xx or a transport error. Returns the parsed JSON or None."""
    t0 = time.monotonic()
    try:
        r = requests.request(method, f"{BASE}{path}", timeout=180, **kwargs)
    except requests.RequestException as e:
        with _lock:
            failures.append((name, f"{type(e).__name__}: {e}"))
        return None
    elapsed = time.monotonic() - t0
    with _lock:
        latencies[name].append(elapsed)
        if not r.ok:
            failures.append((name, f"HTTP {r.status_code}: {r.text[:200]}"))
    return r.json() if r.ok else None


def start_backend(db_path):
    env = dict(os.environ, PROTOTYPE_DB_PATH=db_path, LLM_PROVIDER="idun", IDUN_API_KEY="")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--port", str(PORT), "--log-level", "warning"],
        cwd=REPO, env=env,
    )
    for _ in range(60):
        try:
            requests.get(f"{BASE}/api/questions", timeout=1)
            return proc
        except requests.RequestException:
            time.sleep(0.5)
    proc.terminate()
    sys.exit("Backend didn't come up on port 8100.")


def api(method, path, **kwargs):
    r = requests.request(method, f"{BASE}{path}", timeout=90, **kwargs)
    r.raise_for_status()
    return r.json()


def setup_lecture(students):
    """A fresh lecture with one live question. The throwaway DB may start with a
    pre-seeded active lecture -- end it first."""
    active = api("GET", "/api/lecturer/lectures/active")["lecture"]
    if active:
        api("POST", "/api/lecturer/lecture/finish", json={})
    lecture = api("POST", "/api/lecturer/lectures", json={"label": f"Load test, {students} students"})
    lecture = api("POST", f"/api/lecturer/lectures/{lecture['id']}/open_lobby")
    q = api(
        "POST",
        "/api/lecturer/questions",
        json={
            "title": "Sum the numbers",
            "prompt": "Read space-separated integers and print their sum.",
            "language": "python",
            "test_cases": [
                {"stdin": "1 2 3\n", "expected_stdout": "6"},
                {"stdin": "10\n", "expected_stdout": "10"},
                {"stdin": "-4 4 7\n", "expected_stdout": "7"},
            ],
            "reference_solution": CORRECT,
            "expected_students": students,
            "duration_seconds": 3600,
        },
    )
    assert api("POST", f"/api/lecturer/questions/{q['id']}/validate")["validated"]
    api("POST", f"/api/lecturer/questions/{q['id']}/start")
    return lecture, q["id"]


def background_student(name, qid):
    """Status polling + heartbeats, on the student page's own intervals, for the
    whole run -- independent of whether this student is mid-submit."""
    next_beat = time.monotonic()
    while not stop.is_set():
        call("status", "GET", "/api/lecture/status")
        if time.monotonic() >= next_beat:
            call("activity", "POST", "/api/lecture/activity",
                 json={"student_name": name, "question_id": qid, "edited": True})
            next_beat += HEARTBEAT_S
        stop.wait(STATUS_POLL_S)


def student(name, qid, plan, first_submit_at):
    time.sleep(max(0, first_submit_at - time.monotonic()))
    for i, (code, expected) in enumerate(plan):
        if i:
            time.sleep(random.uniform(3, 8))  # read the hint, fix, resubmit
        res = call("submit", "POST", "/api/submit",
                   json={"student_name": name, "question_id": qid, "source_code": code})
        with _lock:
            submit_results.append((name, expected, res["verdict"] if res else None))


def lecturer(qid):
    while not stop.is_set():
        call("lecturer:submissions", "GET", "/api/lecturer/submissions", params={"question_id": qid})
        call("lecturer:clusters", "GET", "/api/lecturer/clusters", params={"question_id": qid})
        call("lecturer:progress", "GET", f"/api/lecturer/questions/{qid}/progress")
        call("lecturer:activity", "GET", f"/api/lecturer/questions/{qid}/activity")
        stop.wait(LECTURER_POLL_S)


def pct(values, p):
    values = sorted(values)
    return values[min(len(values) - 1, int(round(p / 100 * (len(values) - 1))))]


def report(qid, n_students, wall):
    print(f"\n=== Latency (s), {n_students} students, {wall:.1f}s wall-clock ===")
    print(f"{'endpoint':<24}{'n':>6}{'p50':>9}{'p95':>9}{'max':>9}")
    for name in sorted(latencies):
        v = latencies[name]
        print(f"{name:<24}{len(v):>6}{statistics.median(v):>9.2f}{pct(v, 95):>9.2f}{max(v):>9.2f}")

    print("\n=== Correctness ===")
    ok = True
    wrong = [r for r in submit_results if r[2] != r[1]]
    print(f"Submits: {len(submit_results)}, verdict as expected: {len(submit_results) - len(wrong)}")
    for name, expected, actual in wrong[:10]:
        ok = False
        print(f"  {name}: expected {expected}, got {actual}")

    rows = api("GET", "/api/lecturer/submissions", params={"question_id": qid})
    sent = sum(1 for r in submit_results if r[2] is not None)
    print(f"Stored rows: {len(rows)} (successful submits: {sent})")
    if len(rows) != sent:
        ok = False
    by_student = defaultdict(list)
    for row in rows:
        by_student[row["student_name"]].append(row["attempt_number"])
    bad = {s: sorted(a) for s, a in by_student.items() if sorted(a) != list(range(1, len(a) + 1))}
    print(f"Attempt numbers 1..k per student: {'OK' if not bad else bad}")
    ok = ok and not bad

    print(f"\nRequest failures: {len(failures)}")
    for name, desc in failures[:10]:
        print(f"  {name}: {desc}")
    ok = ok and not failures
    print("\nPASS" if ok else "\nFAIL")
    return ok


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--students", type=int, default=40)
    ap.add_argument("--mode", choices=["burst", "spread"], default="burst")
    ap.add_argument("--spread", type=float, default=60, help="seconds, for --mode spread")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--watch", action="store_true", help="pause before and after, to look in a browser")
    args = ap.parse_args()
    random.seed(args.seed)

    judge0 = os.environ.get("JUDGE0_BASE_URL", "http://localhost:2358")
    try:
        requests.get(f"{judge0}/about", timeout=5).raise_for_status()
    except requests.RequestException as e:
        sys.exit(f"Judge0 isn't reachable at {judge0} ({e}). Start it first.")

    db = Path(tempfile.mkdtemp(prefix="load_test_")) / "load_test.db"
    proc = start_backend(str(db))
    try:
        lecture, qid = setup_lecture(args.students)
        names = [f"Student{i:03d}" for i in range(1, args.students + 1)]
        for name in names:
            api("POST", "/api/lecture/join", json={"code": lecture["join_code"], "student_name": name})
        print(f"Lecture #{lecture['id']}, question {qid!r}, {len(names)} students joined, mode={args.mode}")
        if args.watch:
            print(f"\n  Student page:  {BASE}/student.html   (join code {lecture['join_code']})")
            print(f"  Lecturer page: {BASE}/lecturer.html?question_id={qid}")
            input("\nJoin as a student, have code ready to submit, then press Enter to start the run...")

        weights = [w for _, w, _ in PLANS]
        background = [threading.Thread(target=lecturer, args=(qid,), daemon=True)]
        background += [threading.Thread(target=background_student, args=(n, qid), daemon=True) for n in names]
        for t in background:
            t.start()

        t0 = time.monotonic() + 2  # let the background traffic settle first
        workers = []
        for name in names:
            _, _, plan = random.choices(PLANS, weights)[0]
            offset = random.uniform(0, 1) if args.mode == "burst" else random.uniform(0, args.spread)
            workers.append(threading.Thread(target=student, args=(name, qid, plan, t0 + offset)))
        for t in workers:
            t.start()
        for t in workers:
            t.join()
        wall = time.monotonic() - t0
        stop.set()
        for t in background:
            t.join(timeout=10)

        ok = report(qid, args.students, wall)
        if args.watch:
            input(f"\nLook at {BASE}/lecturer.html?question_id={qid}, then press Enter to end the lecture...")
        api("POST", "/api/lecturer/lecture/finish", json={"current_question_id": qid})
    finally:
        proc.terminate()
        proc.wait(timeout=10)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
