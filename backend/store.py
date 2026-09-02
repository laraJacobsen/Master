"""
SQLite-backed session store. Every submission (student's code, Judge0
results, AI verdict/feedback/discussion point) gets one row. Simple by
design -- this is a lecture-hall MVP (dozens of students, one session at
a time), not a multi-tenant production store.
"""

import os
import sqlite3
import threading

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
        conn.commit()
        conn.close()


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
