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
                lecture_id INTEGER
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
            raise ValueError("No active lecture -- start one from the home dashboard first.")
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


def _lecture_display_label(row: dict) -> str:
    if row.get("label"):
        return row["label"]
    started = datetime.strptime(row["started_at"], "%Y-%m-%d %H:%M:%S")
    return f"Lecture -- {started.strftime('%b %d, %Y')}"


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


def record_join(lecture_id: int, student_name: str) -> None:
    """Records one distinct student joining the lobby -- the UNIQUE
    (lecture_id, student_name) constraint on lecture_joins makes a
    refresh/rejoin from the same student a no-op rather than double-counting
    them in the lobby's live counter (joined_count() below)."""
    with _lock:
        conn = _connect()
        conn.execute(
            "INSERT INTO lecture_joins (lecture_id, student_name) VALUES (?, ?) "
            "ON CONFLICT (lecture_id, student_name) DO NOTHING",
            (lecture_id, student_name),
        )
        conn.commit()
        conn.close()


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
    same defensive shape as close_question()."""
    with _lock:
        conn = _connect()
        conn.execute(
            "UPDATE lectures SET ended_at = datetime('now') WHERE id = ? AND ended_at IS NULL",
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
    """Every question stamped with this lecture_id, in the order they were
    run -- the per-task rows for the lecturer session summary and the
    student recap (see aggregation.py)."""
    with _lock:
        conn = _connect()
        cur = conn.execute(
            "SELECT * FROM questions WHERE lecture_id = ? ORDER BY created_at ASC, rowid ASC",
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
    each still carrying its own lecture_id -- sit in that list forever,
    which is exactly why "closed questions from a previous lecture" were
    still showing up on setup/Manage questions. Defaults to False so the
    student-facing live-question lookup (see questions.py's list_questions(),
    which also calls this) is unaffected -- it only ever has one live
    question at a time regardless."""
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
