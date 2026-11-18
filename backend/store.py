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
import secrets
import sqlite3
import threading
from collections import defaultdict
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
                started_at TEXT,
                lecture_id INTEGER,
                idle_nudge_seconds INTEGER NOT NULL DEFAULT 180,
                output_file TEXT,
                starter_code TEXT,
                hint_ladder TEXT
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
        # See class-progress-visualization-decision.md's activity section --
        # 0 turns the idle nudge off for that question.
        if "idle_nudge_seconds" not in existing_q_columns:
            conn.execute("ALTER TABLE questions ADD COLUMN idle_nudge_seconds INTEGER NOT NULL DEFAULT 180")
        # NULL: grade what the program prints; a file name: grade what it writes
        # to that file (see judge0_client.run_submission's output_file).
        if "output_file" not in existing_q_columns:
            conn.execute("ALTER TABLE questions ADD COLUMN output_file TEXT")
        # What students find in their editor when the task starts, written by
        # the lecturer (helper functions, a skeleton to complete...). NULL: the
        # student page's built-in default for the language (see
        # frontend/src/shared/starterCode.ts). An empty string is a deliberate
        # "start from nothing".
        if "starter_code" not in existing_q_columns:
            conn.execute("ALTER TABLE questions ADD COLUMN starter_code TEXT")
        # JSON list of the task's own wrong-answer hints, attempt 1 first,
        # drafted by backend/hint_ladder.py and edited/approved by the lecturer
        # in setup. NULL: wrong answers get feedback.py's generic hints.
        if "hint_ladder" not in existing_q_columns:
            conn.execute("ALTER TABLE questions ADD COLUMN hint_ladder TEXT")
        # A question that was already `live` before started_at existed (e.g.
        # an existing checkout's seeded sum-ints) would otherwise have no
        # timer zero-point -- backfill it to "now" so its countdown starts
        # fresh from a full duration rather than never counting down at all.
        conn.execute("UPDATE questions SET started_at = datetime('now') WHERE status = 'live' AND started_at IS NULL")

        # `lectures`: a real table (see home-dashboard-scoping-decision),
        # replacing the earlier lecture_seq int + one-row lecture_state
        # counter -- browsing *past* lectures (the home dashboard's history
        # list) needs actual rows, not just a sequence number. `ended_at IS
        # NULL` means "this lecture is currently live"; there's deliberately
        # no separate finished/current-pointer table anymore -- the single-
        # active-lecture invariant (create_lecture()/start_question() below)
        # plus "most recent row by id" (current_lecture_row() below) for
        # "which lecture is current" is the whole state machine.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lectures (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                label TEXT,
                archived INTEGER NOT NULL DEFAULT 0,
                join_code TEXT,
                lobby_opened_at TEXT
            )
            """
        )
        # Migration for DBs created before join_code existed (see the
        # Kahoot-style join-code decision) -- CREATE TABLE IF NOT EXISTS
        # above doesn't touch columns on an already-existing table.
        existing_lecture_columns = {row["name"] for row in conn.execute("PRAGMA table_info(lectures)")}
        if "join_code" not in existing_lecture_columns:
            conn.execute("ALTER TABLE lectures ADD COLUMN join_code TEXT")
        # Backfill a code onto whichever lecture is currently active in an
        # existing DB (there's at most one) -- otherwise an in-progress
        # lecture from before this feature existed would have no code, and
        # the student page's join screen would have nothing valid to accept.
        # Ended lectures are left alone; nobody needs to join one that's over.
        for row in conn.execute("SELECT id FROM lectures WHERE ended_at IS NULL AND join_code IS NULL"):
            conn.execute(
                "UPDATE lectures SET join_code = ? WHERE id = ?", (_generate_join_code(), row["id"])
            )

        # Migration for DBs created before the lobby stage existed (see the
        # lobby-scoping-decision) -- same pattern as join_code above.
        if "lobby_opened_at" not in existing_lecture_columns:
            conn.execute("ALTER TABLE lectures ADD COLUMN lobby_opened_at TEXT")
        # Backfill: an already-active lecture from before this column existed
        # was necessarily already past the lobby stage (there was no lobby
        # gate to have stopped at), so treat it as opened from the start --
        # otherwise it would suddenly become unjoinable/unstartable on
        # upgrade. Ended lectures are left alone, same reasoning as join_code.
        conn.execute(
            "UPDATE lectures SET lobby_opened_at = started_at WHERE ended_at IS NULL AND lobby_opened_at IS NULL"
        )

        # `lecture_joins`: one row per distinct student who's entered the
        # lobby join code for a given lecture -- backs the lobby's live "N
        # joined" counter (join_lobby-scoping-decision.md). The uniqueness
        # constraint is what makes a refresh/rejoin idempotent rather than
        # inflating the count; see api_lecture_join in main.py, the only
        # writer.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS lecture_joins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lecture_id INTEGER NOT NULL,
                student_name TEXT NOT NULL,
                joined_at TEXT NOT NULL DEFAULT (datetime('now')),
                UNIQUE (lecture_id, student_name)
            )
            """
        )
        # The student's secret for this lecture, handed out on join (see
        # join_student()): every student request carries it, and the server
        # takes the student's name from it instead of trusting a typed name.
        # NULL only on rows from before tokens existed -- the next join under
        # that name claims the row.
        if "token" not in {row["name"] for row in conn.execute("PRAGMA table_info(lecture_joins)")}:
            conn.execute("ALTER TABLE lecture_joins ADD COLUMN token TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS lecture_joins_token ON lecture_joins (token)")

        # `student_activity`: one row per student per question, refreshed by
        # the student page's heartbeat (record_activity() below) -- backs the
        # lecturer's active/idle/away status and the automatic idle nudge
        # (class-progress-visualization-decision.md). Only *whether* the
        # student typed is recorded, never what they typed.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS student_activity (
                question_id TEXT NOT NULL,
                student_name TEXT NOT NULL,
                first_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
                last_seen_at TEXT NOT NULL DEFAULT (datetime('now')),
                last_edit_at TEXT,
                nudged_at TEXT,
                nudge_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (question_id, student_name)
            )
            """
        )

        # `raised_issues`: the issues the lecturer chose to show the class
        # (aggregation.raise_issue()), in the order raised. Used to live in
        # aggregation's memory, so any backend restart -- including every
        # `uvicorn --reload` triggered by saving a .py file -- silently
        # took the examples off the students' screens mid-lecture.
        # `students` is the JSON list of student names in the issue when it
        # was raised; `submission_id` is the example shown.
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS raised_issues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id TEXT NOT NULL,
                exec_verdict TEXT NOT NULL,
                error_type TEXT,
                students TEXT NOT NULL,
                submission_id INTEGER NOT NULL
            )
            """
        )
        # `single`: 1 = one submission the lecturer picked from a student's own
        # attempts (any verdict, correct ones included -- see
        # set_submission_shown()), not a discussion point. Shown to the class
        # the same way, but it doesn't mark any discussion point as raised.
        existing_raised_columns = {row["name"] for row in conn.execute("PRAGMA table_info(raised_issues)")}
        if "single" not in existing_raised_columns:
            conn.execute("ALTER TABLE raised_issues ADD COLUMN single INTEGER NOT NULL DEFAULT 0")
        # `position`: the row's place in the question's screen queue -- the
        # lecturer queues several things while the task runs, reorders them,
        # and steps through them one at a time once it's over. Rows from before
        # the queue keep the order they were raised in.
        if "position" not in existing_raised_columns:
            conn.execute("ALTER TABLE raised_issues ADD COLUMN position INTEGER")
            conn.execute("UPDATE raised_issues SET position = id")
        # Which queue entry is on the projector and students' screens right now,
        # per question. No row (or one pointing at a removed entry) means the
        # first in the queue -- see current_queue_entry_id().
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS screen_queue_state (
                question_id TEXT PRIMARY KEY,
                current_entry_id INTEGER
            )
            """
        )

        existing_q_columns = {row["name"] for row in conn.execute("PRAGMA table_info(questions)")}
        if "lecture_seq" in existing_q_columns:
            # Migrating a DB from the lecture_seq/lecture_state scheme: one
            # lectures row per distinct lecture_seq, best-effort started_at/
            # ended_at backfilled from the questions that carried that seq
            # (there's no more precise record of when an old lecture actually
            # wrapped up than "its last task's start time plus that task's
            # own duration"), then questions.lecture_id backfilled and the
            # old column/table dropped.
            has_lecture_state = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='lecture_state'"
            ).fetchone()
            old_state = None
            if has_lecture_state:
                old_state = conn.execute(
                    "SELECT finished, current_seq FROM lecture_state WHERE id = 1"
                ).fetchone()

            seqs = [
                r["lecture_seq"]
                for r in conn.execute(
                    "SELECT DISTINCT lecture_seq FROM questions WHERE lecture_seq IS NOT NULL ORDER BY lecture_seq"
                )
            ]
            seq_to_lecture_id = {}
            for seq in seqs:
                agg = conn.execute(
                    "SELECT MIN(started_at) AS first_started, MAX(started_at) AS last_started, "
                    "MAX(duration_seconds) AS last_duration FROM questions WHERE lecture_seq = ?",
                    (seq,),
                ).fetchone()
                still_live = bool(old_state) and seq == old_state["current_seq"] and not old_state["finished"]
                ended_at = None
                if not still_live and agg["last_started"]:
                    ended_at = conn.execute(
                        "SELECT datetime(?, '+' || ? || ' seconds') AS v",
                        (agg["last_started"], agg["last_duration"] or 0),
                    ).fetchone()["v"]
                cur = conn.execute(
                    "INSERT INTO lectures (started_at, ended_at) VALUES (?, ?)",
                    (agg["first_started"] or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), ended_at),
                )
                seq_to_lecture_id[seq] = cur.lastrowid

            if "lecture_id" not in existing_q_columns:
                conn.execute("ALTER TABLE questions ADD COLUMN lecture_id INTEGER")
            for seq, lecture_id in seq_to_lecture_id.items():
                conn.execute("UPDATE questions SET lecture_id = ? WHERE lecture_seq = ?", (lecture_id, seq))
            conn.execute("ALTER TABLE questions DROP COLUMN lecture_seq")
            if has_lecture_state:
                conn.execute("DROP TABLE lecture_state")
        elif "lecture_id" not in existing_q_columns:
            conn.execute("ALTER TABLE questions ADD COLUMN lecture_id INTEGER")
            # A question that was already live/closed before lecture_id (and
            # lecture_seq before it) ever existed has no real history to
            # recover -- give it one synthetic already-ended lecture row so
            # it isn't just silently excluded from session-summary/carry-
            # forward/recap aggregation forever.
            orphaned = conn.execute(
                "SELECT COUNT(*) AS c FROM questions WHERE status IN ('live', 'closed') AND lecture_id IS NULL"
            ).fetchone()["c"]
            if orphaned:
                fallback_id = conn.execute(
                    "INSERT INTO lectures (started_at, ended_at) VALUES (datetime('now'), datetime('now'))"
                ).lastrowid
                conn.execute(
                    "UPDATE questions SET lecture_id = ? WHERE status IN ('live', 'closed') AND lecture_id IS NULL",
                    (fallback_id,),
                )

        # Drafts left unstarted when a lecture ended used to stay in the shared
        # bank (lecture_id NULL) and resurface in the next lecture -- see
        # end_lecture(). One-time backfill for DBs from before that fix: a
        # draft created during an already-ended lecture is retired under it.
        # Timestamps are whole seconds, so a draft created in the same second
        # a lecture ended and the next one started (finish, then straight into
        # a new lecture) matches both -- it belongs to the newer one, which is
        # what the NOT EXISTS says. Without it, that draft was retired on the
        # next server start.
        conn.execute(
            """
            UPDATE questions SET status = 'skipped', lecture_id = (
                SELECT l.id FROM lectures l
                WHERE l.ended_at IS NOT NULL
                  AND questions.created_at BETWEEN l.started_at AND l.ended_at
                  AND NOT EXISTS (
                      SELECT 1 FROM lectures newer
                      WHERE newer.id > l.id AND newer.started_at <= questions.created_at
                  )
                ORDER BY l.id DESC LIMIT 1
            )
            WHERE status = 'draft' AND lecture_id IS NULL AND EXISTS (
                SELECT 1 FROM lectures l
                WHERE l.ended_at IS NOT NULL
                  AND questions.created_at BETWEEN l.started_at AND l.ended_at
                  AND NOT EXISTS (
                      SELECT 1 FROM lectures newer
                      WHERE newer.id > l.id AND newer.started_at <= questions.created_at
                  )
            )
            """
        )

        # Same invariant as end_lecture(): nothing stays live under a lecture
        # that has already ended (DBs from before that was enforced).
        conn.execute(
            "UPDATE questions SET status = 'closed' WHERE status = 'live' AND lecture_id IN "
            "(SELECT id FROM lectures WHERE ended_at IS NOT NULL)"
        )

        # Seed the original MVP question directly as `live`/validated so a fresh
        # checkout keeps working exactly as before without anyone having to walk
        # it through the setup page first (see smoke_test.py, README.md).
        seeded = conn.execute("SELECT 1 FROM questions WHERE id = 'sum-ints'").fetchone()
        if not seeded:
            # Also gets a join code, already "opened" (see _generate_join_code/
            # create_lecture/open_lobby) so a fresh checkout's student page can
            # actually get past the join screen without anyone having clicked
            # "New lecture" then "Open lobby" first.
            seed_lecture_id = conn.execute(
                "INSERT INTO lectures (started_at, join_code, lobby_opened_at) VALUES (datetime('now'), ?, datetime('now'))",
                (_generate_join_code(),),
            ).lastrowid
            conn.execute(
                """
                INSERT INTO questions
                    (id, title, prompt, language, test_cases, reference_solution,
                     cpu_time_limit_s, memory_limit_kb, extra_packages, line_limit,
                     status, validated, duration_seconds, started_at, lecture_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'live', 1, ?, datetime('now'), ?)
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
                    seed_lecture_id,
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
    if row.get("hint_ladder") is not None and not isinstance(row["hint_ladder"], str):
        row["hint_ladder"] = json.dumps(row["hint_ladder"])
    return row


def _deserialize_question(row: dict) -> dict:
    q = dict(row)
    q["test_cases"] = json.loads(q["test_cases"])
    q["extra_packages"] = json.loads(q["extra_packages"])
    q["validated"] = bool(q["validated"])
    q["hint_ladder"] = json.loads(q["hint_ladder"]) if q.get("hint_ladder") else None
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
                 expected_students, duration_seconds, idle_nudge_seconds, output_file, starter_code,
                 hint_ladder)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                row.get("idle_nudge_seconds", 180),
                row.get("output_file"),
                row.get("starter_code"),
                row.get("hint_ladder"),
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
    """Flips a question live, stamps `started_at` as the timer's zero point,
    and tags it with the currently active lecture -- see
    api_lecturer_start_question/api_lecturer_lecture_next in main.py, both
    of which call this. Requires an active lecture to already exist
    (create_lecture(), the home dashboard's "New lecture" action) -- there's
    no more implicit "starting a question right after the last lecture ended
    begins a new one" behavior; the home dashboard is now the only place a
    lecture starts. Also requires that lecture's lobby to have been opened
    (open_lobby() below) -- the lobby is where students join and get
    counted *before* anything is timed, so a question can't go live and
    start a countdown out from under a lobby that was never actually
    opened. Raises ValueError in either missing-prerequisite case.

    Always closes out any other currently-live question first -- there's
    only ever one active lecture, so "live" should never mean more than one
    question at once. A hard invariant here rather than trusting every
    caller to remember to close the previous one (a caller that doesn't --
    e.g. the lobby's "Start lecture" reached a second time after a question
    was already started -- would otherwise leave two questions live at
    once instead of one advancing to the next)."""
    with _lock:
        conn = _connect()
        active = conn.execute(
            "SELECT id, lobby_opened_at FROM lectures WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if not active:
            conn.close()
            raise ValueError("No active lecture. Start one from the home dashboard first.")
        if not active["lobby_opened_at"]:
            conn.close()
            raise ValueError("Open the lobby before starting the lecture.")
        conn.execute("UPDATE questions SET status = 'closed' WHERE status = 'live' AND id != ?", (question_id,))
        conn.execute(
            "UPDATE questions SET status = 'live', started_at = ?, lecture_id = ? WHERE id = ?",
            (datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), active["id"], question_id),
        )
        conn.commit()
        conn.close()


def delete_question(question_id: str) -> None:
    """Removes a draft question outright -- callers (see main.py) are
    responsible for rejecting this once a question has gone live, same
    division of responsibility as update_question(). Safe as a hard delete:
    a still-draft question can't have any submissions (see api_submit's
    status == "live" check), so there's nothing orphaned to worry about."""
    with _lock:
        conn = _connect()
        conn.execute("DELETE FROM questions WHERE id = ?", (question_id,))
        conn.commit()
        conn.close()


def close_question(question_id: str) -> None:
    """Ends a question's live window (timer expired and/or the lecturer moved
    on) without deleting it -- closed questions no longer accept submissions
    (see api_submit's status == "live" check) but stay around for the
    lecturer to review."""
    update_question(question_id, {"status": "closed"})


def end_question_now(question_id: str) -> None:
    """Runs a live question's timer out early (the lecturer's "End task now")
    by shortening duration_seconds to the time already elapsed. Deliberately
    not close_question(): the question stays live, so it goes through the
    exact same "time's up" path as a timer that ran out on its own --
    students' unsubmitted code gets auto-submitted, and "Show on full screen"
    examples reach their waiting screens. Moving on is still "Next task"."""
    row = get_question_row(question_id)
    if not row or row["status"] != "live" or not row.get("started_at"):
        return
    started = datetime.strptime(row["started_at"], "%Y-%m-%d %H:%M:%S")
    elapsed = int((datetime.utcnow() - started).total_seconds())
    if elapsed < row["duration_seconds"]:
        update_question(question_id, {"duration_seconds": max(0, elapsed)})


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


def count_ready_drafts() -> int:
    """How many validated drafts "Next task" could still start -- the
    not-yet-run tasks in the live dashboard's "Task N of M"."""
    with _lock:
        conn = _connect()
        n = conn.execute("SELECT COUNT(*) FROM questions WHERE status = 'draft' AND validated = 1").fetchone()[0]
        conn.close()
        return n


def _lecture_display_label(row: dict) -> str:
    if row.get("label"):
        return row["label"]
    started = datetime.strptime(row["started_at"], "%Y-%m-%d %H:%M:%S")
    return f"Lecture on {started.strftime('%b %d, %Y')}"


def _serialize_lecture(row: dict) -> dict:
    lecture = dict(row)
    lecture["archived"] = bool(lecture["archived"])
    lecture["display_label"] = _lecture_display_label(lecture)
    return lecture


def _generate_join_code() -> str:
    """A 6-digit Kahoot-style PIN the lecturer reads/projects and students
    type in to enter the lecture. Digits only (not the question/rubric
    validation package allow-list -- unrelated) so it's easy to read aloud
    and type on a phone keyboard. No uniqueness check against past lectures:
    only one lecture is ever live at a time (see create_lecture's docstring),
    so only the current code needs to be unambiguous."""
    return f"{secrets.randbelow(1_000_000):06d}"


def create_lecture(label: str = None) -> dict:
    """Starts a brand-new lecture -- the home dashboard's "New lecture"
    action, and now the ONLY place a lecture starts (see start_question()'s
    docstring: there's no more implicit trigger). Refuses if one is already
    active (`ended_at IS NULL`) -- this backend supports exactly one live
    lecture at a time, and the home dashboard is expected to offer "Resume"
    instead of a second "New lecture" whenever this would raise.

    Also mints this lecture's join code (see _generate_join_code) -- a soft,
    Kahoot-style entry gate for the student page, not real access control
    (see the "No auth" known simplification in README.md; /api/submit itself
    stays open)."""
    with _lock:
        conn = _connect()
        if conn.execute("SELECT 1 FROM lectures WHERE ended_at IS NULL").fetchone():
            conn.close()
            raise ValueError("A lecture is already in progress.")
        cur = conn.execute(
            "INSERT INTO lectures (started_at, label, join_code) VALUES (datetime('now'), ?, ?)",
            (label, _generate_join_code()),
        )
        lecture_id = cur.lastrowid
        conn.commit()
        row = conn.execute("SELECT * FROM lectures WHERE id = ?", (lecture_id,)).fetchone()
        conn.close()
        return _serialize_lecture(dict(row))


def check_join_code(code: str):
    """Validates a student-typed code against the active lecture's join
    code. Returns the active lecture dict on a match, None if there's no
    active lecture or the code doesn't match (case/whitespace-insensitive --
    students will paste/type it inconsistently)."""
    lecture = get_active_lecture()
    if not lecture or not lecture.get("join_code"):
        return None
    if code.strip().upper() != lecture["join_code"].strip().upper():
        return None
    return lecture


def open_lobby(lecture_id: int) -> dict:
    """Opens the lobby: from this point on, students can actually join (see
    api_lecture_join in main.py, which now also gates on this) and starting
    the first question is allowed (see start_question()'s docstring). Before
    this, a lecture exists (so the lecturer can author/edit/delete questions
    against it) but is otherwise inert -- no code shown, nothing joinable,
    nothing timed. Idempotent: calling it again on an already-open lobby is
    a no-op, not an error, so a lecturer navigating back to setup and then
    back to the lobby doesn't re-stamp the open time."""
    with _lock:
        conn = _connect()
        conn.execute(
            "UPDATE lectures SET lobby_opened_at = datetime('now') "
            "WHERE id = ? AND ended_at IS NULL AND lobby_opened_at IS NULL",
            (lecture_id,),
        )
        conn.commit()
        row = conn.execute("SELECT * FROM lectures WHERE id = ?", (lecture_id,)).fetchone()
        conn.close()
        return _serialize_lecture(dict(row)) if row else None


class NameTaken(ValueError):
    """Another student in this lecture already joined under that name."""


def join_student(lecture_id: int, student_name: str, token: str | None = None) -> dict:
    """Records one student joining the lecture and returns their identity,
    {"student_name", "token"}. The token is what every later student request
    carries (see main.py's _student); the name is only for display.

    One name per student per lecture, compared case-insensitively ("ola" and
    "Ola" are the same student on the lecturer's dashboard): a name that's
    already taken raises NameTaken -- unless `token` is that student's own
    token, i.e. the same browser rejoining after a refresh or a closed tab,
    which gets the same identity back (and the lobby counter doesn't grow).
    A name from before tokens existed (token NULL) is claimed by whoever
    joins under it next."""
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT id, student_name, token FROM lecture_joins WHERE lecture_id = ? AND lower(student_name) = lower(?)",
            (lecture_id, student_name),
        ).fetchone()
        if row and row["token"] and not (token and secrets.compare_digest(row["token"], token)):
            conn.close()
            raise NameTaken(student_name)
        if row and row["token"]:
            conn.close()
            return {"student_name": row["student_name"], "token": row["token"]}
        new_token = secrets.token_urlsafe(24)
        if row:
            conn.execute("UPDATE lecture_joins SET token = ? WHERE id = ?", (new_token, row["id"]))
            student_name = row["student_name"]
        else:
            conn.execute(
                "INSERT INTO lecture_joins (lecture_id, student_name, token) VALUES (?, ?, ?)",
                (lecture_id, student_name, new_token),
            )
        conn.commit()
        conn.close()
        return {"student_name": student_name, "token": new_token}


def student_for_token(token: str):
    """{"lecture_id", "student_name"} of the student holding this token, or None."""
    if not token:
        return None
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT lecture_id, student_name FROM lecture_joins WHERE token = ?", (token,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None


def joined_count(lecture_id: int) -> int:
    """How many distinct students have joined this lecture's lobby -- the
    lobby view's live counter, polled the same way the live task dashboard
    polls submission progress."""
    with _lock:
        conn = _connect()
        count = conn.execute(
            "SELECT COUNT(*) AS c FROM lecture_joins WHERE lecture_id = ?", (lecture_id,)
        ).fetchone()["c"]
        conn.close()
        return count


def get_lecture_row(lecture_id: int):
    with _lock:
        conn = _connect()
        row = conn.execute("SELECT * FROM lectures WHERE id = ?", (lecture_id,)).fetchone()
        conn.close()
        return _serialize_lecture(dict(row)) if row else None


def get_active_lecture():
    """The one lecture currently in progress (`ended_at IS NULL`), or None --
    what the home dashboard checks to decide "New lecture" vs. "Resume live
    lecture"."""
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT * FROM lectures WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
        conn.close()
        return _serialize_lecture(dict(row)) if row else None


def current_lecture_row():
    """The most relevant lecture for "what should /api/lecture/status,
    /api/lecture/recap, and the default lecture/summary view point at right
    now" -- the active lecture if one exists, else whichever lecture most
    recently ended. Since a lectures row is only ever created by
    create_lecture() (no more implicit trigger -- see start_question()), the
    newest row by id is always exactly this: still live, or the one that
    just ended and hasn't been replaced by a new "New lecture" click yet."""
    with _lock:
        conn = _connect()
        row = conn.execute("SELECT * FROM lectures ORDER BY id DESC LIMIT 1").fetchone()
        conn.close()
        return _serialize_lecture(dict(row)) if row else None


def end_lecture(lecture_id: int) -> None:
    """Marks a lecture's live window over -- the "Finish lecture"/"End
    session" action. A no-op if it's already ended or isn't the active one,
    same defensive shape as close_question().

    Also retires the drafts still sitting in this lecture's question bank
    (never started, so lecture_id is still NULL) as `skipped`, tagged with
    this lecture. Without that, ending a lecture early left its unstarted
    tasks in the shared bank, where the next lecture's setup page and "Next
    task" picked them up as if they belonged to it. `skipped` questions are
    kept (not deleted) but never listed, started, or counted as run tasks
    (see questions_for_lecture())."""
    with _lock:
        conn = _connect()
        cur = conn.execute(
            "UPDATE lectures SET ended_at = datetime('now') WHERE id = ? AND ended_at IS NULL",
            (lecture_id,),
        )
        if cur.rowcount:
            # Hard invariant, not left to the caller passing the current
            # question: a task still live after its lecture ended would be
            # served to the *next* lecture's students (live_question_row()
            # isn't lecture-scoped).
            conn.execute("UPDATE questions SET status = 'closed' WHERE status = 'live'")
            conn.execute(
                "UPDATE questions SET status = 'skipped', lecture_id = ? WHERE status = 'draft' AND lecture_id IS NULL",
                (lecture_id,),
            )
        conn.commit()
        conn.close()


def set_lecture_archived(lecture_id: int, value: bool) -> None:
    """Hides (or restores) a lecture from the default history list without
    touching its data -- for junk/test lectures in a dev DB that isn't wiped
    between runs (see the home-dashboard-scoping-decision). Never deletes
    anything."""
    with _lock:
        conn = _connect()
        conn.execute("UPDATE lectures SET archived = ? WHERE id = ?", (1 if value else 0, lecture_id))
        conn.commit()
        conn.close()


def delete_lecture(lecture_id: int) -> None:
    """Removes a lecture outright -- callers (see main.py) are responsible
    for confirming no question has ever gone live under it first, the same
    division of responsibility as delete_question(). Safe as a hard delete
    under that condition: a question only ever gets tagged with a
    lecture_id at start_question() time, so no started question means no
    submissions and nothing else in the app references this lecture. Also
    clears its lecture_joins rows -- there's no submission data behind a
    join, just "someone entered the lobby.\""""
    with _lock:
        conn = _connect()
        conn.execute("DELETE FROM lecture_joins WHERE lecture_id = ?", (lecture_id,))
        conn.execute("DELETE FROM lectures WHERE id = ?", (lecture_id,))
        conn.commit()
        conn.close()


def list_lectures(include_archived: bool = False) -> list:
    """Lecture history for the home dashboard: newest first, each annotated
    with how many tasks it had and a short submission-stats snapshot (total
    distinct-student submissions summed across its tasks, plus a verdict
    breakdown) -- aggregate only, no student names/ids anywhere in this view
    (see the product decision against any per-student identification here)."""
    with _lock:
        conn = _connect()
        query = "SELECT * FROM lectures"
        if not include_archived:
            query += " WHERE archived = 0"
        query += " ORDER BY id DESC"
        lectures = [_serialize_lecture(dict(r)) for r in conn.execute(query)]
        conn.close()

    for lecture in lectures:
        questions = questions_for_lecture(lecture["id"])
        lecture["task_count"] = len(questions)
        submitted_total = 0
        verdict_counts = defaultdict(int)
        for q in questions:
            latest_by_student = {}
            for row in all_submissions(q["id"]):
                latest_by_student.setdefault(row["student_name"], row)
            submitted_total += len(latest_by_student)
            for row in latest_by_student.values():
                verdict_counts[row.get("verdict") or "error"] += 1
        lecture["submitted_total"] = submitted_total
        lecture["verdict_counts"] = dict(verdict_counts)
    return lectures


def lecture_totals() -> dict:
    """All-time counts across every lecture ever run (including archived --
    this is a lifetime tally, not "what's currently visible") -- the home
    dashboard's optional all-time stats line."""
    with _lock:
        conn = _connect()
        lectures_run = conn.execute("SELECT COUNT(*) AS c FROM lectures").fetchone()["c"]
        total_submissions = conn.execute("SELECT COUNT(*) AS c FROM submissions").fetchone()["c"]
        conn.close()
        return {"lectures_run": lectures_run, "total_submissions": total_submissions}


def questions_for_lecture(lecture_id: int) -> list:
    """Every question that actually ran under this lecture_id, in the order
    they were run -- the per-task rows for the lecturer session summary and
    the student recap (see aggregation.py). Excludes drafts retired as
    `skipped` when the lecture ended (see end_lecture())."""
    with _lock:
        conn = _connect()
        cur = conn.execute(
            "SELECT * FROM questions WHERE lecture_id = ? AND status != 'skipped' "
            "ORDER BY created_at ASC, rowid ASC",
            (lecture_id,),
        )
        rows = [_deserialize_question(dict(r)) for r in cur.fetchall()]
        conn.close()
        return rows


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


def list_question_rows(status: str = None, current_lecture_only: bool = False) -> list:
    """`current_lecture_only` scopes to the setup page's "this lecture's
    question bank": never-started drafts (lecture_id IS NULL -- reusable
    across lectures until started) plus whatever's tied to the currently
    active lecture. Without it, past lectures' already-closed questions --
    each still carrying its own lecture_id -- would otherwise sit in that
    list forever, which is exactly what made "New lecture" look like it
    wasn't actually starting fresh (see the home-dashboard bug report: a
    previous lecture's "Double It", answers and all, still showing up on
    setup after starting a brand-new lecture with nothing in it yet).
    Defaults to False so the student-facing live-question lookup (see
    questions.py's list_questions(), which also calls this) is unaffected --
    it only ever has one live question at a time regardless."""
    with _lock:
        conn = _connect()
        clauses = []
        params = []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if current_lecture_only:
            active = conn.execute(
                "SELECT id FROM lectures WHERE ended_at IS NULL ORDER BY id DESC LIMIT 1"
            ).fetchone()
            if active:
                clauses.append("(lecture_id IS NULL OR lecture_id = ?)")
                params.append(active["id"])
            else:
                clauses.append("lecture_id IS NULL")
        # rowid DESC breaks ties within the same created_at second (same
        # reasoning as all_submissions()'s "id DESC" -- two questions can be
        # created in the same second).
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        cur = conn.execute(f"SELECT * FROM questions {where} ORDER BY created_at DESC, rowid DESC", params)
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


def record_activity(question_id: str, student_name: str, edited: bool) -> dict:
    """One heartbeat from a student's editor (see api_lecture_activity in
    main.py). Timestamps are the server's own clock, so a student's skewed
    laptop clock can't make them look idle. Typing clears any earlier nudge,
    so the next idle stretch can earn a fresh one. Returns the updated row."""
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO student_activity (question_id, student_name) VALUES (?, ?) "
            "ON CONFLICT (question_id, student_name) DO UPDATE SET last_seen_at = datetime('now')",
            (question_id, student_name),
        )
        if edited:
            conn.execute(
                "UPDATE student_activity SET last_edit_at = datetime('now'), nudged_at = NULL "
                "WHERE question_id = ? AND student_name = ?",
                (question_id, student_name),
            )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM student_activity WHERE question_id = ? AND student_name = ?",
            (question_id, student_name),
        ).fetchone()
        conn.close()
        return dict(row)


def mark_nudged(question_id: str, student_name: str) -> None:
    with _lock:
        conn = _connect()
        conn.execute(
            "UPDATE student_activity SET nudged_at = datetime('now'), nudge_count = nudge_count + 1 "
            "WHERE question_id = ? AND student_name = ?",
            (question_id, student_name),
        )
        conn.commit()
        conn.close()


def activity_rows(question_id: str) -> list:
    with _lock:
        conn = _connect()
        rows = [
            dict(r)
            for r in conn.execute("SELECT * FROM student_activity WHERE question_id = ?", (question_id,))
        ]
        conn.close()
        return rows


def joined_names(lecture_id: int) -> list:
    """Everyone who entered this lecture's join code -- lets the lecturer's
    activity view list students who joined but never opened the editor,
    not just the ones who've sent a heartbeat."""
    with _lock:
        conn = _connect()
        names = [
            r["student_name"]
            for r in conn.execute(
                "SELECT student_name FROM lecture_joins WHERE lecture_id = ? ORDER BY student_name", (lecture_id,)
            )
        ]
        conn.close()
        return names


def has_solved(question_id: str, student_name: str) -> bool:
    with _lock:
        conn = _connect()
        row = conn.execute(
            "SELECT 1 FROM submissions WHERE question_id = ? AND student_name = ? AND verdict = 'correct' LIMIT 1",
            (question_id, student_name),
        ).fetchone()
        conn.close()
        return row is not None


def raised_issue_rows(question_id: str) -> list:
    """The question's raised discussion points (see aggregation.raise_issue()),
    in queue order, each with `students` as a frozenset of names. Single
    submissions shown on their own (set_submission_shown()) are left out --
    they don't raise a discussion point."""
    return [r for r in queue_rows(question_id) if not r["single"]]


def queue_rows(question_id: str) -> list:
    """Everything queued for the class's screens on this question -- raised
    discussion points and single submissions alike -- in queue order, each with
    `students` as a frozenset of names."""
    with _lock:
        conn = _connect()
        rows = _queue_rows(conn, question_id)
        conn.close()
        return rows


def _queue_rows(conn, question_id: str) -> list:
    return [
        {**dict(r), "students": frozenset(json.loads(r["students"]))}
        for r in conn.execute(
            "SELECT * FROM raised_issues WHERE question_id = ? ORDER BY position, id", (question_id,)
        )
    ]


def get_queue_entry(entry_id: int):
    with _lock:
        conn = _connect()
        row = conn.execute("SELECT * FROM raised_issues WHERE id = ?", (entry_id,)).fetchone()
        conn.close()
        return dict(row) if row else None


def _append_queue_entry(conn, question_id: str, exec_verdict: str, error_type, students_json: str, submission_id: int, single: int) -> int:
    next_position = conn.execute(
        "SELECT COALESCE(MAX(position), 0) + 1 FROM raised_issues WHERE question_id = ?", (question_id,)
    ).fetchone()[0]
    cur = conn.execute(
        "INSERT INTO raised_issues (question_id, exec_verdict, error_type, students, submission_id, single, position) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (question_id, exec_verdict, error_type, students_json, submission_id, single, next_position),
    )
    return cur.lastrowid


def _delete_queue_entries(conn, ids) -> None:
    """Deletes queue entries, moving any question's on-screen pointer that
    pointed at one of them to the entry after it (or, at the end of the queue,
    the one before) -- so taking down what's on screen shows the next thing
    instead of jumping back to the start."""
    ids = set(ids)
    if not ids:
        return
    question_ids = {
        r["question_id"]
        for r in conn.execute(
            f"SELECT question_id FROM raised_issues WHERE id IN ({','.join('?' * len(ids))})", tuple(ids)
        )
    }
    for question_id in question_ids:
        order = [r["id"] for r in _queue_rows(conn, question_id)]
        current = _current_entry_id(conn, question_id, order)
        if current in ids:
            i = order.index(current)
            after = [e for e in order[i + 1 :] if e not in ids]
            before = [e for e in order[:i] if e not in ids]
            _set_current(conn, question_id, after[0] if after else (before[-1] if before else None))
    conn.executemany("DELETE FROM raised_issues WHERE id = ?", [(i,) for i in ids])


def _current_entry_id(conn, question_id: str, order: list):
    row = conn.execute(
        "SELECT current_entry_id FROM screen_queue_state WHERE question_id = ?", (question_id,)
    ).fetchone()
    stored = row["current_entry_id"] if row else None
    if stored in order:
        return stored
    return order[0] if order else None


def _set_current(conn, question_id: str, entry_id) -> None:
    conn.execute(
        "INSERT INTO screen_queue_state (question_id, current_entry_id) VALUES (?, ?) "
        "ON CONFLICT(question_id) DO UPDATE SET current_entry_id = excluded.current_entry_id",
        (question_id, entry_id),
    )


def current_queue_entry_id(question_id: str):
    """The queue entry on screen for this question (the first one unless the
    lecturer has moved on), or None if nothing is queued."""
    with _lock:
        conn = _connect()
        order = [r["id"] for r in _queue_rows(conn, question_id)]
        current = _current_entry_id(conn, question_id, order)
        conn.close()
        return current


def set_current_queue_entry(question_id: str, entry_id: int) -> None:
    with _lock:
        conn = _connect()
        _set_current(conn, question_id, entry_id)
        conn.commit()
        conn.close()


def step_current_queue_entry(question_id: str, step: int) -> None:
    """Moves what's on screen `step` places along the queue, stopping at either end."""
    with _lock:
        conn = _connect()
        order = [r["id"] for r in _queue_rows(conn, question_id)]
        current = _current_entry_id(conn, question_id, order)
        if current is not None:
            i = max(0, min(len(order) - 1, order.index(current) + step))
            _set_current(conn, question_id, order[i])
            conn.commit()
        conn.close()


def move_queue_entry(entry_id: int, index: int) -> None:
    """Moves one entry to `index` (0-based, clamped) in its question's queue."""
    with _lock:
        conn = _connect()
        row = conn.execute("SELECT question_id FROM raised_issues WHERE id = ?", (entry_id,)).fetchone()
        if row:
            order = [r["id"] for r in _queue_rows(conn, row["question_id"]) if r["id"] != entry_id]
            order.insert(max(0, min(len(order), index)), entry_id)
            conn.executemany(
                "UPDATE raised_issues SET position = ? WHERE id = ?", [(i + 1, e) for i, e in enumerate(order)]
            )
            conn.commit()
        conn.close()


def delete_queue_entry(entry_id: int) -> None:
    with _lock:
        conn = _connect()
        _delete_queue_entries(conn, [entry_id])
        conn.commit()
        conn.close()


def add_raised_issue(question_id: str, exec_verdict: str, error_type, students: set, submission_id: int) -> int:
    """Adds a raised discussion point to the end of the question's screen
    queue and returns its entry id. Only one entry is on screen at a time
    (requested 2026-11-17 -- two at once each got half the projector and came
    out too small to read); the lecturer steps through the rest."""
    students_json = json.dumps(sorted(students))
    with _lock:
        conn = _connect()
        entry_id = _append_queue_entry(conn, question_id, exec_verdict, error_type, students_json, submission_id, 0)
        conn.commit()
        conn.close()
        return entry_id


def delete_raised_issues(ids: list) -> None:
    if not ids:
        return
    with _lock:
        conn = _connect()
        _delete_queue_entries(conn, ids)
        conn.commit()
        conn.close()


def shown_submission_ids(question_id: str, single_only: bool = False) -> list:
    """Every submission queued for the class's screens on this question, in
    queue order -- raised discussion points' examples and single submissions
    alike (or only the latter). May repeat an id if both picked the same one."""
    return [r["submission_id"] for r in queue_rows(question_id) if r["single"] or not single_only]


def set_submission_shown(submission: dict, shown: bool):
    """Queues (or takes out of the queue) one student's submission for the
    class's screens -- the live dashboard's "Show on screen" in a student's
    code drawer. Any verdict, so the lecturer can put up a correct solution
    too. Returns the entry id when queueing (the existing one if it was
    already queued), else None."""
    with _lock:
        conn = _connect()
        existing = [
            r["id"]
            for r in conn.execute(
                "SELECT id FROM raised_issues WHERE single = 1 AND submission_id = ?", (submission["id"],)
            )
        ]
        entry_id = None
        if shown and existing:
            entry_id = existing[0]
        elif shown:
            entry_id = _append_queue_entry(
                conn,
                submission["question_id"],
                submission.get("exec_verdict") or "",
                submission.get("error_type"),
                json.dumps([submission["student_name"]]),
                submission["id"],
                1,
            )
        elif existing:
            _delete_queue_entries(conn, existing)
        conn.commit()
        conn.close()
        return entry_id
