#!/usr/bin/env python3
"""Dev-only: runs a live mock lecture against the RUNNING app, with synthetic students
who keep answering, so the live dashboard always has something to show.

THIS IS SYNTHETIC DATA. The lecture is labeled "[Demo] Live mock lecture" and every
program is written by this script -- keep it out of anything reported as research data.

What it does, all over HTTP against the real backend (and so the real Judge0):
  1. Creates the lecture with five tasks -- three that read stdin, two that read data
     files (one graded on a file the program writes) -- validates each, and drafts its
     wrong-answer hints (skipped if no language model is configured).
  2. Opens the lobby, lets the students join, and starts task 1.
  3. Watches the lecture: whenever a task goes live (you press "Next task" on the
     dashboard), the students start on it -- heartbeats while they work, then a few
     wrong submissions and usually a right one, spread over the first couple of minutes.
  4. Stops when you finish the lecture (or on Ctrl-C).

Needs the backend (default http://localhost:8000) and Judge0 running.

Usage:
    python3 demo_live_lecture.py
    python3 demo_live_lecture.py --students 16 --spread 120
    python3 demo_live_lecture.py --finish-active     # end a running lecture first
"""

import argparse
import os
import random
import sys
import threading
import time
from pathlib import Path

import requests

REPO = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO))
import seed_demo_lectures as stdin_seed  # noqa: E402
import seed_file_lecture as file_seed  # noqa: E402

LABEL = "[Demo] Live mock lecture"
NAMES = stdin_seed.STUDENTS

# --- Wrong answers for the two file tasks (appended to their starter code) ----------
FILE_BUGS = {
    "Gradebook averages": [
        # Not sorted by name.
        'by_student = {}\nfor student, subject, score in scores:\n    by_student.setdefault(student, []).append(score)\n'
        'for student in by_student:\n    marks = by_student[student]\n    print(f"{student} {sum(marks) / len(marks):.1f}")\n'
        'print(f"class {sum(s for _, _, s in scores) / len(scores):.1f}")\n',
        # Integer division.
        'by_student = {}\nfor student, subject, score in scores:\n    by_student.setdefault(student, []).append(score)\n'
        'for student in sorted(by_student):\n    marks = by_student[student]\n    print(student, sum(marks) // len(marks))\n'
        'print("class", sum(s for _, _, s in scores) // len(scores))\n',
        # Class average = average of the student averages.
        'by_student = {}\nfor student, subject, score in scores:\n    by_student.setdefault(student, []).append(score)\n'
        'avgs = []\nfor student in sorted(by_student):\n    marks = by_student[student]\n    avgs.append(sum(marks) / len(marks))\n'
        '    print(f"{student} {avgs[-1]:.1f}")\nprint(f"class {sum(avgs) / len(avgs):.1f}")\n',
        # KeyError: appends before the student has a list.
        'by_student = {}\nfor student, subject, score in scores:\n    by_student[student].append(score)\n'
        'for student in sorted(by_student):\n    marks = by_student[student]\n    print(f"{student} {sum(marks) / len(marks):.1f}")\n',
    ],
    "Warehouse restock": [
        # Prints instead of writing restock.txt.
        'left = {item: q for item, (q, m) in stock.items()}\nfor item, amount in orders:\n    left[item] -= amount\n'
        'for item in sorted(stock):\n    if left[item] < stock[item][1]:\n        print(item, 2 * stock[item][1] - left[item])\n',
        # <= instead of <.
        'left = {item: q for item, (q, m) in stock.items()}\nfor item, amount in orders:\n    left[item] -= amount\n'
        'lines = [f"{i} {2 * stock[i][1] - left[i]}" for i in sorted(stock) if left[i] <= stock[i][1]]\n'
        'write_lines("restock.txt", lines or ["nothing to restock"])\n',
        # Restocks up to the minimum, not twice it.
        'left = {item: q for item, (q, m) in stock.items()}\nfor item, amount in orders:\n    left[item] -= amount\n'
        'lines = [f"{i} {stock[i][1] - left[i]}" for i in sorted(stock) if left[i] < stock[i][1]]\n'
        'write_lines("restock.txt", lines or ["nothing to restock"])\n',
        # An item ordered twice only comes off the stock once (= instead of -=).
        'left = {item: q for item, (q, m) in stock.items()}\nfor item, amount in orders:\n    left[item] = stock[item][0] - amount\n'
        'lines = [f"{i} {2 * stock[i][1] - left[i]}" for i in sorted(stock) if left[i] < stock[i][1]]\n'
        'write_lines("restock.txt", lines or ["nothing to restock"])\n',
    ],
}


def stdin_task(key, duration=10 * 60):
    ex = stdin_seed.EXERCISES[key]
    return {
        "title": ex["title"],
        "payload": {
            "prompt": ex["prompt"],
            "reference_solution": ex["reference"],
            "test_cases": [{"stdin": i, "expected_stdout": o} for i, o in ex["tests"]],
            "duration_seconds": duration,
        },
        "correct": ex["correct"],
        "wrong": [code for _, shapes in ex["bugs"] for code in shapes],
    }


def file_task(title, rng, duration=15 * 60):
    task = next(t for t in file_seed.TASKS if t["title"] == title)
    tests = []
    for files in task["tests"](rng):
        expected = file_seed.run_reference(file_seed.reference(task), files, task.get("output_file"))
        tests.append({"stdin": "", "expected_stdout": expected,
                      "files": [{"name": n, "content": c} for n, c in files.items()]})
    return {
        "title": title,
        "payload": {
            "prompt": task["prompt"],
            "reference_solution": file_seed.reference(task),
            "starter_code": task["starter"],
            "output_file": task.get("output_file"),
            "test_cases": tests,
            "duration_seconds": duration,
        },
        "correct": [file_seed.reference(task)],
        "wrong": [task["starter"] + bug for bug in FILE_BUGS[title]],
    }


class Api:
    def __init__(self, base):
        self.base = base.rstrip("/")
        # Each student's join token -- student calls send it (as_student) instead of a name.
        self.tokens = {}
        # The lecturer password, if the server has one (see backend/auth.py).
        password = os.environ.get("LECTURER_PASSWORD")
        self.headers = {"X-Lecturer-Token": password} if password else {}

    def as_student(self, name):
        return {"X-Student-Token": self.tokens[name]}

    def __call__(self, method, path, **kw):
        kw["headers"] = {**self.headers, **kw.get("headers", {})}
        r = requests.request(method, self.base + path, timeout=120, **kw)
        if r.status_code != 200:
            raise RuntimeError(f"{method} {path} -> {r.status_code}: {r.text[:300]}")
        return r.json()


def set_up(api, args, rng):
    active = api("GET", "/api/lecturer/lectures/active")
    if active["lecture"]:
        if not args.finish_active:
            sys.exit(f'Lecture "{active["lecture"]["display_label"]}" is running. Finish it first, '
                     "or rerun with --finish-active.")
        api("POST", "/api/lecturer/lecture/finish", json={"current_question_id": active["live_question_id"]})
        print(f'Finished "{active["lecture"]["display_label"]}"')
    waiting = [q for q in api("GET", "/api/lecturer/questions") if q["status"] == "draft" and q["validated"]]
    if waiting:
        sys.exit("These checked drafts would run before the demo's tasks on \"Next task\": "
                 + ", ".join(q["title"] for q in waiting) + ". Delete them first.")

    tasks = [
        stdin_task("sum"),
        file_task("Gradebook averages", rng),
        stdin_task("palindrome"),
        file_task("Warehouse restock", rng),
        stdin_task("second"),
    ]
    lecture = api("POST", "/api/lecturer/lectures", json={"label": LABEL})
    print(f'Created "{LABEL}" (lecture #{lecture["id"]}, join code {lecture.get("join_code")})')
    by_id = {}
    for t in tasks:
        p = t["payload"]
        q = api("POST", "/api/lecturer/questions", json={
            "title": t["title"], "language": "python", "expected_students": args.students, **p})
        v = api("POST", f"/api/lecturer/questions/{q['id']}/validate")
        if not v["validated"]:
            sys.exit(f'"{t["title"]}" failed validation: {v}')
        note = "no hints (drafting failed)"
        try:
            hints = api("POST", "/api/lecturer/hints/draft", json={
                "prompt": p["prompt"], "language": "python",
                "reference_solution": p["reference_solution"], "starter_code": p.get("starter_code")})["hints"]
            api("PUT", f"/api/lecturer/questions/{q['id']}", json={"hint_ladder": hints})
            note = "hints drafted"
        except RuntimeError as e:
            note = f"no hints ({str(e)[:80]})"
        kind = "files" if p.get("starter_code") else "stdin"
        print(f'  {t["title"]} ({kind}): validated, {note}')
        by_id[q["id"]] = t

    api("POST", f'/api/lecturer/lectures/{lecture["id"]}/open_lobby')
    code = api("GET", f'/api/lecturer/lectures/{lecture["id"]}')["join_code"]
    students = rng.sample(NAMES, args.students)
    for name in students:
        api.tokens[name] = api("POST", "/api/lecture/join", json={"code": code, "student_name": name})["token"]
    print(f"Lobby open, {len(students)} students joined (code {code})")
    started = api("POST", "/api/lecturer/lecture/next", json={})["started"]
    print(f'Started task 1: {started["title"]}')
    return by_id, students


def work_on(api, task, qid, name, rng, spread, stop):
    """One student on one task: heartbeats while working, wrong tries, maybe a right one."""
    solves = rng.random() < 0.7
    n_wrong = rng.choices([0, 1, 2, 3], weights=[30, 35, 22, 13])[0] if solves else rng.choice([1, 2, 2, 3])
    first_bug = rng.choice(task["wrong"])
    attempts = [first_bug if rng.random() < 0.6 else rng.choice(task["wrong"]) for _ in range(n_wrong)]
    if solves:
        attempts.append(rng.choice(task["correct"]))
    if rng.random() < 0.08:
        attempts = []  # never submits: shows up as idle on the dashboard
    times = sorted(rng.uniform(10, spread) for _ in attempts)
    start = time.monotonic()
    pending = list(zip(times, attempts))
    last_beat = 0.0
    while not stop.is_set():
        now = time.monotonic() - start
        if now - last_beat >= 10:
            last_beat = now
            try:
                api("POST", "/api/lecture/activity", headers=api.as_student(name),
                    json={"question_id": qid, "edited": bool(pending) and rng.random() < 0.8})
            except RuntimeError:
                pass
        if pending and now >= pending[0][0]:
            _, code = pending.pop(0)
            try:
                r = api("POST", "/api/submit", headers=api.as_student(name), json={"question_id": qid, "source_code": code})
                if r["verdict"] == "correct":
                    pending = []
            except RuntimeError as e:
                if "409" in str(e):
                    return  # task closed
        stop.wait(1)


def watch(api, by_id, students, args, rng):
    current, stop, done = None, threading.Event(), set()
    while True:
        status = api("GET", "/api/lecture/status")
        q = status.get("question")
        qid = q["id"] if q and q.get("seconds_remaining", 0) > 0 else None
        if status.get("finished") or (status.get("lecture_id") is None and current):
            stop.set()
            print("Lecture finished -- stopping.")
            return
        if qid != current:
            stop.set()
            stop = threading.Event()
            current = qid
            if qid in by_id and qid not in done:
                done.add(qid)
                print(f'{time.strftime("%H:%M:%S")} "{by_id[qid]["title"]}" is live: '
                      f"{len(students)} students start answering")
                for name in students:
                    threading.Thread(target=work_on, daemon=True, args=(
                        api, by_id[qid], qid, name, random.Random(rng.random()), args.spread, stop)).start()
        time.sleep(3)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--base", default="http://localhost:8000")
    ap.add_argument("--students", type=int, default=14)
    ap.add_argument("--spread", type=float, default=150, help="seconds over which a task's submissions arrive")
    ap.add_argument("--finish-active", action="store_true")
    ap.add_argument("--seed", type=int, default=None)
    args = ap.parse_args()
    rng = random.Random(args.seed)
    api = Api(args.base)
    by_id, students = set_up(api, args, rng)
    try:
        watch(api, by_id, students, args, rng)
    except KeyboardInterrupt:
        print("Stopped.")


if __name__ == "__main__":
    main()
