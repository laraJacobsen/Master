"""
SQLite-backed session store. Every submission (student's code, Judge0
results, AI verdict/feedback/discussion point) gets one row. Simple by
design -- this is a lecture-hall MVP (dozens of students, one session at
a time), not a multi-tenant production store.

Also holds the `questions` table (see landing-page-scoping-decision.md):
a question starts life as a `draft` a lecturer is configuring on the
setup/landing page, must pass a validation preview (run its rubric
against a reference solution) before it can `start`, and becomes `live`
only then -- students can only see/submit against `live` questions
(backend/questions.py enforces the student-facing filter). Once live, a
question's config is locked (see `update_question`) so submissions already
graded against it stay comparable to later ones.
"""

import json
import os
import re
import sqlite3
import threading
from datetime import datetime

DB_PATH = os.environ.get(
    "PROTOTYPE_DB_PATH",
    os.path.join(os.path.dirname(__file__), "prototype.db"),
)

_lock = threading.Lock()


def _connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _lock:
        conn = _connect()
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                student_name TEXT NOT NULL,
                question_id TEXT NOT NULL,
                language TEXT NOT NULL,
                source_code TEXT NOT NULL,
                attempt_number INTEGER,
                tests_passed INTEGER,
                tests_total INTEGER,
                verdict TEXT,
                error_type TEXT,
                exec_verdict TEXT,
                rejection_reason TEXT,
                feedback TEXT,
                discussion_point TEXT,
                raw_test_results TEXT
            )
            """
        )
        # Migration for DBs created before attempt_number/exec_verdict/
        # rejection_reason existed -- CREATE TABLE IF NOT EXISTS above doesn't
        # touch columns on an already-existing table.
        existing = {row["name"] for row in conn.execute("PRAGMA table_info(submissions)")}
        for column, sqltype in (
            ("attempt_number", "INTEGER"),
            ("exec_verdict", "TEXT"),
            ("rejection_reason", "TEXT"),
        ):
            if column not in existing:
                conn.execute(f"ALTER TABLE submissions ADD COLUMN {column} {sqltype}")

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS questions (
                id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT (datetime('now')),
                title TEXT NOT NULL,
                prompt TEXT NOT NULL,
                language TEXT NOT NULL,
                test_cases TEXT NOT NULL,
                reference_solution TEXT,
                cpu_time_limit_s REAL NOT NULL DEFAULT 5,
                memory_limit_kb INTEGER NOT NULL DEFAULT 128000,
                extra_packages TEXT NOT NULL DEFAULT '[]',
                line_limit INTEGER NOT NULL DEFAULT 200,
                status TEXT NOT NULL DEFAULT 'draft',
                validated INTEGER NOT NULL DEFAULT 0,
                expected_students INTEGER,
                duration_seconds INTEGER NOT NULL DEFAULT 600,
                started_at TEXT
            )
            """
        )
        # Migration for DBs created before expected_students/duration_seconds/
        # started_at existed (see live-submission-progress-scoping-decision.md
        # and the task-timer feature) -- CREATE TABLE IF NOT EXISTS above
        # doesn't touch columns on an already-existing table.
        existing_q_columns = {row["name"] for row in conn.execute("PRAGMA table_info(questions)")}
        if "expected_students" not in existing_q_columns:
            conn.execute("ALTER TABLE questions ADD COLUMN expected_students INTEGER")
        if "duration_seconds" not in existing_q_columns:
            conn.execute("ALTER TABLE questions ADD COLUMN duration_seconds INTEGER NOT NULL DEFAULT 600")
        if "started_at" not in existing_q_columns:
            conn.execute("ALTER TABLE questions ADD COLUMN started_at TEXT")
        # A question that was already `live` before started_at existed (e.g.
        # an existing checkout's seeded sum-ints) would otherwise have no
        # timer zero-point -- backfill it to "now" so its countdown starts
        # fresh from a full duration rather than never counting down at all.
        conn.execute("UPDATE questions SET started_at = datetime('now') WHERE status = 'live' AND started_at IS NULL")

        # One-row table tracking whether the lecturer has explicitly ended the
        # whole lecture (distinct from "between tasks" -- see the "Next
        # task"/"Finish lecture" flow in main.py). Reset to 0 whenever any
        # question is started.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lecture_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                finished INTEGER NOT NULL DEFAULT 0
            )
            """
        )
        if not conn.execute("SELECT 1 FROM lecture_state WHERE id = 1").fetchone():
            conn.execute("INSERT INTO lecture_state (id, finished) VALUES (1, 0)")

        # Seed the original MVP question directly as `live`/validated so a fresh
        # checkout keeps working exactly as before without anyone having to walk
        # it through the setup page first (see smoke_test.py, README.md).
        seeded = conn.execute("SELECT 1 FROM questions WHERE id = 'sum-ints'").fetchone()
        if not seeded:
            conn.execute(
                """
                INSERT INTO questions
                    (id, title, prompt, language, test_cases, reference_solution,
                     cpu_time_limit_s, memory_limit_kb, extra_packages, line_limit,
                     status, validated, duration_seconds, started_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'live', 1, ?, datetime('now'))
                """,
                (
                    "sum-ints",
                    "Sum of Integers",
                    "Read a single line of space-separated integers from standard input "
                    "and print their sum on one line.",
                    "python",
                    json.dumps(
                        [
                            {"stdin": "1 2 3\n", "expected_stdout": "6"},
                            {"stdin": "10 20 30 40\n", "expected_stdout": "100"},
                            {"stdin": "-5 5\n", "expected_stdout": "0"},
                            {"stdin": "7\n", "expected_stdout": "7"},
                            {"stdin": "1000000 2000000\n", "expected_stdout": "3000000"},
                        ]
                    ),
                    "print(sum(int(x) for x in input().split()))",
                    5,
                    128000,
                    "[]",
                    200,
                    600,
                ),
            )

        conn.commit()
        conn.close()


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(title: str) -> str:
    slug = _SLUG_RE.sub("-", title.strip().lower()).strip("-")
    return slug or "question"


def _serialize_question(fields: dict) -> dict:
    row = dict(fields)
    if "test_cases" in row and not isinstance(row["test_cases"], str):
        row["test_cases"] = json.dumps(row["test_cases"])
    if "extra_packages" in row and not isinstance(row["extra_packages"], str):
        row["extra_packages"] = json.dumps(row["extra_packages"])
    return row


def _deserialize_question(row: dict) -> dict:
    q = dict(row)
    q["test_cases"] = json.loads(q["test_cases"])
    q["extra_packages"] = json.loads(q["extra_packages"])
    q["validated"] = bool(q["validated"])
    return q


def create_question(fields: dict) -> str:
    """Inserts a new draft question, generating a unique id from its title.
    Returns the new question's id."""
    row = _serialize_question(fields)
    with _lock:
        conn = _connect()
        base_slug = _slugify(row["title"])
        question_id = base_slug
        suffix = 2
        while conn.execute("SELECT 1 FROM questions WHERE id = ?", (question_id,)).fetchone():
            question_id = f"{base_slug}-{suffix}"
            suffix += 1
        conn.execute(
            """
            INSERT INTO questions
                (id, title, prompt, language, test_cases, reference_solution,
                 cpu_time_limit_s, memory_limit_kb, extra_packages, line_limit,
                 expected_students, duration_seconds)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                question_id,
                row["title"],
                row["prompt"],
                row["language"],
                row["test_cases"],
                row.get("reference_solution"),
                row.get("cpu_time_limit_s", 5),
                row.get("memory_limit_kb", 128000),
                row.get("extra_packages", "[]"),
                row.get("line_limit", 200),
                row.get("expected_students"),
                row.get("duration_seconds", 600),
            ),
        )
        conn.commit()
        conn.close()
        return question_id


def update_question(question_id: str, fields: dict) -> None:
    """Updates only the given fields on a still-draft question. Callers (see
    main.py) are responsible for rejecting edits to a question that's already
    live -- this function itself doesn't check status, so it can also be used
    internally by set_validated/set_status below."""
    if not fields:
        return
    row = _serialize_question(fields)
    columns = ", ".join(f"{k} = ?" for k in row)
    with _lock:
        conn = _connect()
        conn.execute(
            f"UPDATE questions SET {columns} WHERE id = ?",
            (*row.values(), question_id),
        )
        conn.commit()
        conn.close()


def set_validated(question_id: str, value: bool) -> None:
    update_question(question_id, {"validated": 1 if value else 0})


def set_status(question_id: str, status: str) -> None:
    update_question(question_id, {"status": status})


def start_question(question_id: str) -> None:
    """Flips a question live and stamps `started_at` as the timer's zero
    point -- see api_lecturer_start_question/api_lecturer_lecture_next in
    main.py, both of which call this. Also clears the lecture-finished flag,
    since starting a question (the first one, or via "Next task") means the
    lecture is (still) in progress."""
    update_question(question_id, {"status": "live", "started_at": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")})
    set_lecture_finished(False)


def close_question(question_id: str) -> None:
    """Ends a question's live window (timer expired and/or the lecturer moved
    on) without deleting it -- closed questions no longer accept submissions
    (see api_submit's status == "live" check) but stay around for the
    lecturer to review."""
    update_question(question_id, {"status": "closed"})


def next_draft_question():
    """The earliest-created, validated draft question -- what "Next task"
    (see api_lecturer_lecture_next in main.py) starts next. Lecture order is
    simply question creation order."""
    with _lock:
        conn = _connect()
        cur = conn.execute(
            "SELECT * FROM questions WHERE status = 'draft' AND validated = 1 "
            "ORDER BY created_at ASC, rowid ASC LIMIT 1"
        )
        row = cur.fetchone()
        conn.close()
        return _deserialize_question(dict(row)) if row else None


def get_lecture_finished() -> bool:
    with _lock:
        conn = _connect()
        row = conn.execute("SELECT finished FROM lecture_state WHERE id = 1").fetchone()
        conn.close()
        return bool(row["finished"]) if row else False


def set_lecture_finished(value: bool) -> None:
    with _lock:
        conn = _connect()
        conn.execute("UPDATE lecture_state SET finished = ? WHERE id = 1", (1 if value else 0,))
        conn.commit()
        conn.close()


def live_question_row():
    """The single question currently live, if any -- this prototype runs one
    lecture at a time, so at most one question is live at once (see
    api_lecture_status in main.py, the student page's poll target)."""
    with _lock:
        conn = _connect()
        cur = conn.execute("SELECT * FROM questions WHERE status = 'live' ORDER BY started_at DESC LIMIT 1")
        row = cur.fetchone()
        conn.close()
        return _deserialize_question(dict(row)) if row else None


def get_question_row(question_id: str):
    with _lock:
        conn = _connect()
        cur = conn.execute("SELECT * FROM questions WHERE id = ?", (question_id,))
        row = cur.fetchone()
        conn.close()
        return _deserialize_question(dict(row)) if row else None


def list_question_rows(status: str = None) -> list:
    with _lock:
        conn = _connect()
        if status:
            cur = conn.execute(
                "SELECT * FROM questions WHERE status = ? ORDER BY created_at DESC", (status,)
            )
        else:
            cur = conn.execute("SELECT * FROM questions ORDER BY created_at DESC")
        rows = [_deserialize_question(dict(r)) for r in cur.fetchall()]
        conn.close()
        return rows


def next_attempt_number(student_name: str, question_id: str) -> int:
    with _lock:
        conn = _connect()
        cur = conn.execute(
            "SELECT COUNT(*) AS c FROM submissions WHERE student_name = ? AND question_id = ?",
            (student_name, question_id),
        )
        count = cur.fetchone()["c"]
        conn.close()
        return count + 1


def save_submission(row: dict) -> int:
    with _lock:
        conn = _connect()
        cur = conn.execute(
            """
            INSERT INTO submissions
                (student_name, question_id, language, source_code, attempt_number,
                 tests_passed, tests_total, verdict, error_type, exec_verdict,
                 rejection_reason, feedback, discussion_point, raw_test_results)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["student_name"],
                row["question_id"],
                row["language"],
                row["source_code"],
                row["attempt_number"],
                row["tests_passed"],
                row["tests_total"],
                row["verdict"],
                row["error_type"],
                row["exec_verdict"],
                row["rejection_reason"],
                row["feedback"],
                row["discussion_point"],
                row["raw_test_results"],
            ),
        )
        conn.commit()
        new_id = cur.lastrowid
        conn.close()
        return new_id


def all_submissions(question_id: str = None) -> list:
    with _lock:
        conn = _connect()
        # id DESC breaks ties within the same created_at second (real
        # scenario when several students submit at once).
        if question_id:
            cur = conn.execute(
                "SELECT * FROM submissions WHERE question_id = ? ORDER BY created_at DESC, id DESC",
                (question_id,),
            )
        else:
            cur = conn.execute("SELECT * FROM submissions ORDER BY created_at DESC, id DESC")
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows


def get_submission(sub_id: int):
    with _lock:
        conn = _connect()
        cur = conn.execute("SELECT * FROM submissions WHERE id = ?", (sub_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row) if row else None


def distinct_student_count(question_id: str) -> int:
    """Distinct students who've submitted anything (including a rejected
    submission) for this question -- the numerator for the live "X/N
    submitted" counter (see live-submission-progress-scoping-decision.md).
    A student resubmitting doesn't inflate this, same reasoning as cluster
    counts in aggregation.py."""
    with _lock:
        conn = _connect()
        cur = conn.execute(
            "SELECT COUNT(DISTINCT student_name) AS c FROM submissions WHERE question_id = ?",
            (question_id,),
        )
        count = cur.fetchone()["c"]
        conn.close()
        return count
