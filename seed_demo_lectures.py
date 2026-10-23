#!/usr/bin/env python3
"""Dev-only: fills a database with realistic DEMO lectures, so the history page's
"Needs revisiting" ranking, the end-of-lecture summaries and the per-task
dashboards have enough data to look at and sanity-check.

THIS IS SYNTHETIC DATA. Every lecture it creates is labeled "[Demo] ..." and every
program it submits was written for this script -- not a student submission. Keep it
out of anything reported as research data (the clustering ground truth and the
spot-check rounds in feedback-research/ come from real sources; see their docs).

What's real about it: everything after "a student submits this code" runs through the
actual app over HTTP (FastAPI TestClient) -- lecture/lobby/join, question creation and
validation, /api/submit's grading, hint tiers and stored test results, end-task and
finish -- so the data has exactly the shape production writes. The one stand-in is
Judge0: each program is run locally with this machine's Python instead, and the result
is handed back in Judge0's own response format (same idea as smoke_test.py's fake).

Each lecture has a different difficulty (the chance a student eventually solves a task),
so the ranking has something to rank. Several bugs come in two or three differently
written versions with identical output, which exercises output-signature clustering.
Deterministic (fixed random seed). Timestamps are backdated to weekly lectures so the
history reads like a semester.

Usage:
    python3 seed_demo_lectures.py                       # backend/prototype.db
    python3 seed_demo_lectures.py --archive-existing    # also archive every non-demo
                                                        # lecture (ends an active one)
    python3 seed_demo_lectures.py --db path/to/other.db

Backs the database up next to itself before touching it.
"""

import argparse
import base64
import os
import random
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO = Path(__file__).resolve().parent
SEED = 20261015
DEMO_PREFIX = "[Demo] "

# One cohort, the same students every week (so per-student recaps make sense too).
STUDENTS = [
    "Amalie", "Bjørn", "Camilla", "Daniel", "Emma", "Filip", "Guro", "Henrik", "Ingrid",
    "Jonas", "Karoline", "Lars", "Maja", "Nikolai", "Olivia", "Petter", "Ragnhild",
    "Sindre", "Thea", "Ulrik", "Vilde", "William",
]
EXPECTED_STUDENTS = 24  # the lecturer's typed-in class size -- a couple never show up

# --- Exercises: reference solution, test cases, correct variants, bug pool -----------
# Bugs are (name, [code, ...]): a list with several entries is the SAME wrong behavior
# written differently -- they print identical output on every test case below.
EXERCISES = {
    "sum": {
        "title": "Sum of integers",
        "prompt": "Read a line of space-separated integers and print their sum.",
        "reference": "print(sum(int(x) for x in input().split()))",
        "tests": [("1 2 3\n", "6"), ("10 20 30 40\n", "100"), ("-5 5\n", "0"), ("7\n", "7")],
        "correct": [
            "print(sum(int(x) for x in input().split()))",
            "nums = input().split()\ntotal = 0\nfor n in nums:\n    total += int(n)\nprint(total)",
            "print(sum(map(int, input().split())))",
        ],
        "bugs": [
            ("plus-one", [
                "nums = input().split()\nprint(sum(int(n) for n in nums) + 1)",
                "total = 1\nfor n in input().split():\n    total += int(n)\nprint(total)",
            ]),
            ("drop-last", ["nums = input().split()\nprint(sum(int(n) for n in nums[:-1]))"]),
            ("first-only", ["nums = input().split()\nprint(int(nums[0]))"]),
            ("string-concat", [
                "print(''.join(input().split()))",
                "nums = input().split()\nresult = ''\nfor n in nums:\n    result += n\nprint(result)",
            ]),
            ("syntax", ["nums = input().split(\nprint(sum(int(n) for n in nums))"]),
            ("name-typo", ["nums = input().split()\nprint(sum(int(n) for n in num))"]),
        ],
    },
    "double": {
        "title": "Double it",
        "prompt": "Read one integer and print it doubled.",
        "reference": "print(int(input()) * 2)",
        "tests": [("3\n", "6"), ("10\n", "20"), ("0\n", "0"), ("-4\n", "-8")],
        "correct": [
            "print(int(input()) * 2)",
            "n = int(input())\nprint(n + n)",
            "print(2 * int(input()))",
        ],
        "bugs": [
            ("string-repeat", [
                "print(input() * 2)",
                "x = input()\nprint(x * 2)",
            ]),
            # Converts after repeating: same output as string-repeat on positive
            # numbers, but not on 0 or negatives -- a separate behavior.
            ("int-after-repeat", ["print(int(input().strip() * 2))"]),
            ("plus-two", ["print(int(input()) + 2)"]),
            ("squared", ["n = int(input())\nprint(n * n)", "print(int(input()) ** 2)"]),
        ],
    },
    "palindrome": {
        "title": "Palindrome check",
        "prompt": "Read a line and print True if it reads the same backwards, ignoring case and spaces, else False.",
        "reference": 's = input().lower().replace(" ", "")\nprint(s == s[::-1])',
        "tests": [("Race car\n", "True"), ("hello\n", "False"), ("Was it a car or a cat I saw\n", "True"),
                  ("ab\n", "False")],
        "correct": [
            's = input().lower().replace(" ", "")\nprint(s == s[::-1])',
            't = "".join(input().split()).lower()\nprint(t == "".join(reversed(t)))',
        ],
        "bugs": [
            ("no-lower", ['s = input().replace(" ", "")\nprint(s == s[::-1])']),
            ("no-strip", ['s = input().lower()\nprint(s == s[::-1])']),
            ("no-normalize", ["s = input()\nprint(s == s[::-1])", "t = input()\nprint(t[::-1] == t)"]),
            ("off-by-one", [
                's = input().lower().replace(" ", "")\nok = True\nfor i in range(len(s) // 2):\n'
                '    if s[i] != s[len(s) - i - 2]:\n        ok = False\nprint(ok)'
            ]),
        ],
    },
    "vowels": {
        "title": "Count vowels",
        "prompt": "Read a line and print how many vowels (a, e, i, o, u, any case) it has. 'y' is not a vowel.",
        "reference": 'print(sum(1 for ch in input().lower() if ch in "aeiou"))',
        "tests": [("Ivy is Cute\n", "4"), ("AEIOU\n", "5"), ("rhythm\n", "0"), ("Programming\n", "3")],
        "correct": [
            'print(sum(1 for ch in input().lower() if ch in "aeiou"))',
            'count = 0\nfor ch in input().lower():\n    if ch in "aeiou":\n        count += 1\nprint(count)',
        ],
        "bugs": [
            ("case-sensitive", [
                'print(sum(1 for ch in input() if ch in "aeiou"))',
                'count = 0\nfor ch in input():\n    if ch in "aeiou":\n        count += 1\nprint(count)',
            ]),
            ("counts-y", ['print(sum(1 for ch in input().lower() if ch in "aeiouy"))']),
            ("skips-last", [
                's = input().lower()\ncount = 0\nfor i in range(len(s) - 1):\n    if s[i] in "aeiou":\n'
                '        count += 1\nprint(count)'
            ]),
        ],
    },
    "second": {
        "title": "Second largest",
        "prompt": "Read space-separated integers and print the second-largest distinct value.",
        "reference": "nums = [int(x) for x in input().split()]\nprint(sorted(set(nums), reverse=True)[1])",
        "tests": [("4 1 7 7 3 9 9 2\n", "7"), ("1 2\n", "1"), ("5 5 3\n", "3"), ("9 10 8\n", "9")],
        "correct": [
            "nums = [int(x) for x in input().split()]\nprint(sorted(set(nums), reverse=True)[1])",
            "nums = set(int(x) for x in input().split())\nnums.remove(max(nums))\nprint(max(nums))",
        ],
        "bugs": [
            ("no-dedup", [
                "nums = [int(x) for x in input().split()]\nprint(sorted(nums, reverse=True)[1])",
                "nums = sorted(int(x) for x in input().split())\nprint(nums[-2])",
            ]),
            ("ascending", ["nums = [int(x) for x in input().split()]\nprint(sorted(set(nums))[1])"]),
            ("prints-largest", ["nums = [int(x) for x in input().split()]\nprint(max(nums))"]),
            ("no-int", ["nums = input().split()\nprint(sorted(set(nums), reverse=True)[1])"]),
        ],
    },
}

# Four weekly lectures. solve_p: chance a student who submits eventually gets it right;
# skip_p: chance a joined student never submits that task.
LECTURES = [
    {"label": "Week 2: Input and arithmetic", "date": "2026-09-22", "tasks": ["sum", "double"],
     "solve_p": 0.88, "skip_p": 0.04},
    {"label": "Week 3: Working with strings", "date": "2026-09-29", "tasks": ["palindrome", "vowels"],
     "solve_p": 0.6, "skip_p": 0.1},
    {"label": "Week 4: Lists and sorting", "date": "2026-10-06", "tasks": ["second", "sum"],
     "solve_p": 0.35, "skip_p": 0.18},
    {"label": "Week 5: Review", "date": "2026-10-13", "tasks": ["double", "vowels", "second"],
     "solve_p": 0.62, "skip_p": 0.08},
]


# --- Judge0 stand-in -------------------------------------------------------------------
def _b64(s):
    return base64.b64encode((s or "").encode()).decode()


def fake_post(url, params=None, json=None, headers=None, timeout=None):
    """Runs the submission locally and answers in Judge0's response shape."""
    if not url.endswith("/submissions"):
        raise ConnectionError("seed script: no network calls besides the Judge0 stand-in")
    source = base64.b64decode(json["source_code"]).decode()
    stdin = base64.b64decode(json.get("stdin") or "").decode()
    try:
        proc = subprocess.run([sys.executable, "-c", source], input=stdin, capture_output=True,
                              text=True, timeout=3)
        status = {"id": 3, "description": "Accepted"} if proc.returncode == 0 else \
            {"id": 11, "description": "Runtime Error (NZEC)"}
        stdout, stderr, code = proc.stdout, proc.stderr, proc.returncode
    except subprocess.TimeoutExpired:
        status, stdout, stderr, code = {"id": 5, "description": "Time Limit Exceeded"}, "", "", None
    resp = MagicMock()
    resp.raise_for_status = lambda: None
    resp.json.return_value = {
        "status": status, "stdout": _b64(stdout), "stderr": _b64(stderr) if stderr else None,
        "compile_output": None, "message": None, "time": "0.02", "memory": 3500, "exit_code": code,
    }
    return resp


# --- Student behavior ------------------------------------------------------------------
def attempts_for(rng, exercise, solve_p):
    """The programs one student submits for one task, in order. A struggling student
    usually sticks with one bug (sometimes resubmitting it unchanged) or wanders to a
    second one; most who solve it get there after zero to two wrong tries."""
    bug_name, shapes = rng.choice(exercise["bugs"])
    shape = rng.choice(shapes)
    wrong = []
    solves = rng.random() < solve_p
    n_wrong = rng.choices([0, 1, 2, 3], weights=[45, 30, 17, 8])[0] if solves else rng.choice([1, 1, 2, 2, 3, 4])
    for _ in range(n_wrong):
        if wrong and rng.random() < 0.25:
            bug_name, shapes = rng.choice(exercise["bugs"])  # tries something else, still wrong
            shape = rng.choice(shapes)
        wrong.append(shape)
    return wrong + ([rng.choice(exercise["correct"])] if solves else [])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--db", default=str(REPO / "backend" / "prototype.db"))
    ap.add_argument("--archive-existing", action="store_true",
                    help="archive every lecture that isn't a demo lecture (ends an active one first)")
    args = ap.parse_args()

    db = Path(args.db)
    if db.exists():
        backup = db.with_name(f"{db.stem}-backup-{datetime.now():%Y-%m-%d-%H%M%S}.db")
        shutil.copy2(db, backup)
        print(f"Backed up {db.name} -> {backup.name}")

    os.environ["PROTOTYPE_DB_PATH"] = str(db)
    os.environ["LLM_PROVIDER"] = "idun"  # with no key below: no Label calls from a seed script
    os.environ["IDUN_API_KEY"] = ""
    sys.path.insert(0, str(REPO))

    with patch("backend.judge0_client.requests.post", side_effect=fake_post):
        from fastapi.testclient import TestClient
        from backend.main import app

        with TestClient(app) as client:
            def ok(r):
                assert r.status_code == 200, (r.request.url, r.status_code, r.text)
                return r.json()

            existing = ok(client.get("/api/lecturer/lectures", params={"include_archived": True}))
            if any(l["label"] and l["label"].startswith(DEMO_PREFIX) for l in existing):
                sys.exit("Demo lectures already exist in this database -- not adding a second set.")

            active = ok(client.get("/api/lecturer/lectures/active"))
            if active["lecture"]:
                if not args.archive_existing:
                    sys.exit("A lecture is active. Finish it first, or rerun with --archive-existing.")
                ok(client.post("/api/lecturer/lecture/finish",
                               json={"current_question_id": active["live_question_id"]}))
                print(f"Finished the active lecture #{active['lecture']['id']}")

            if args.archive_existing:
                for lecture in existing:
                    if not lecture["archived"]:
                        ok(client.post(f"/api/lecturer/lectures/{lecture['id']}/archive"))
                print(f"Archived {sum(1 for l in existing if not l['archived'])} existing lecture(s) "
                      "(hidden, not deleted -- 'Show archived' brings them back)")

            rng = random.Random(SEED)
            for spec in LECTURES:
                lecture = ok(client.post("/api/lecturer/lectures", json={"label": DEMO_PREFIX + spec["label"]}))
                ok(client.post(f"/api/lecturer/lectures/{lecture['id']}/open_lobby"))
                present = [s for s in STUDENTS if rng.random() > 0.08]  # a few absent each week
                for name in present:
                    ok(client.post("/api/lecture/join", json={"code": lecture["join_code"], "student_name": name}))

                question_ids = []
                for key in spec["tasks"]:
                    ex = EXERCISES[key]
                    q = ok(client.post("/api/lecturer/questions", json={
                        "title": ex["title"], "prompt": ex["prompt"], "language": "python",
                        "test_cases": [{"stdin": i, "expected_stdout": o} for i, o in ex["tests"]],
                        "reference_solution": ex["reference"], "expected_students": EXPECTED_STUDENTS,
                        "duration_seconds": 600,
                    }))
                    v = ok(client.post(f"/api/lecturer/questions/{q['id']}/validate"))
                    assert v["validated"], (ex["title"], v)
                    question_ids.append((q["id"], ex))

                current = None
                n_subs = 0
                for qid, ex in question_ids:
                    started = ok(client.post("/api/lecturer/lecture/next", json={"current_question_id": current}))
                    assert started["started"]["id"] == qid, started
                    current = qid
                    for name in present:
                        if rng.random() < spec["skip_p"]:
                            continue
                        for code in attempts_for(rng, ex, spec["solve_p"]):
                            ok(client.post("/api/submit", json={"student_name": name, "question_id": qid,
                                                               "source_code": code}))
                            n_subs += 1
                    ok(client.post(f"/api/lecturer/questions/{qid}/end_now"))
                ok(client.post("/api/lecturer/lecture/finish", json={"current_question_id": current}))
                backdate(db, lecture["id"], spec["date"], [qid for qid, _ in question_ids], rng)
                print(f"  #{lecture['id']} {DEMO_PREFIX}{spec['label']}: {len(present)} students, "
                      f"{len(question_ids)} tasks, {n_subs} submissions")

            review = ok(client.get("/api/lecturer/lectures/review"))
            print("\nNeeds revisiting, as the history page will show it:")
            for r in review:
                if r["enough_data"]:
                    print(f"  {r['solve_rate']:.0%} solved  {r['display_label']}")


def backdate(db, lecture_id, date, question_ids, rng):
    """Moves one lecture to its weekly slot (10:15 on `date`, UTC) and spreads its
    submissions over each task's 10 minutes, so the history and the dashboards read
    like real sessions instead of everything happening within one second."""
    start = datetime.strptime(date + " 10:15:00", "%Y-%m-%d %H:%M:%S")
    fmt = "%Y-%m-%d %H:%M:%S"
    conn = sqlite3.connect(db)
    end = start + timedelta(minutes=10 + 15 * len(question_ids))
    conn.execute("UPDATE lectures SET started_at = ?, lobby_opened_at = ?, ended_at = ? WHERE id = ?",
                 ((start - timedelta(minutes=5)).strftime(fmt), (start - timedelta(minutes=3)).strftime(fmt),
                  end.strftime(fmt), lecture_id))
    conn.execute("UPDATE lecture_joins SET joined_at = ? WHERE lecture_id = ?",
                 ((start - timedelta(minutes=2)).strftime(fmt), lecture_id))
    for i, qid in enumerate(question_ids):
        q_start = start + timedelta(minutes=5 + 15 * i)
        conn.execute("UPDATE questions SET started_at = ?, created_at = ? WHERE id = ?",
                     (q_start.strftime(fmt), (start - timedelta(days=1)).strftime(fmt), qid))
        for sub_id, attempt in conn.execute(
            "SELECT id, attempt_number FROM submissions WHERE question_id = ?", (qid,)
        ).fetchall():
            t = q_start + timedelta(seconds=60 + attempt * 110 + rng.randint(0, 100))
            conn.execute("UPDATE submissions SET created_at = ? WHERE id = ?", (t.strftime(fmt), sub_id))
    conn.commit()
    conn.close()


if __name__ == "__main__":
    main()
