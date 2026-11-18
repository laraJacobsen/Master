"""
FastAPI backend for the interactive-lecture prototype.

Flow per submission:
  1. Student POSTs code to /api/submit
  2. Code runs against the question's test cases on Judge0 (SYNC calls)
  3. ai_feedback.judge_and_feedback() classifies the result (verdict, exec_verdict,
     hint text) -- fully deterministic, no model in the loop (see ai_feedback.py)
  4. Everything is saved to SQLite
  5. The student gets pass/fail + a tiered hint back immediately
  6. The lecturer page polls /api/lecturer/submissions and sees it appear, and
     /api/lecturer/clusters for talking points (one per cluster of students who hit
     the same issue, not per submission -- see aggregation.py)

Run with:
    JUDGE0_BASE_URL=http://localhost:2358 uvicorn backend.main:app --reload --port 8000
from the /root/prototype directory (see README.md).
"""

import json
import logging
import os
from datetime import datetime

import anyio
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend import auth, store
from backend.code_shape import with_shape
from backend.aggregation import (
    carry_forward_discussion_points,
    cluster_submissions,
    lecture_review,
    raise_issue,
    screen_position,
    screen_queue,
    shown_examples,
    session_summary,
    student_recap,
)
from backend import test_files
from backend.hint_ladder import clean_ladder, draft_hint_ladder
from backend.ai_feedback import _traceback_for, judge_and_feedback
from backend.judge0_client import Judge0Error, run_submission, run_test_cases
from backend.questions import get_question, list_questions
from backend.validation import pre_execution_check, reads_input, DEFAULT_LINE_LIMIT

app = FastAPI(title="Interactive Lecture Prototype")

# The pages are served by this app (and proxied by Vite in dev), so every call
# is same-origin and needs no CORS. Other origins only if an operator lists
# them (comma-separated) -- never "*", which let any website call the API.
_cors_origins = [o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Reachable without being logged in: logging in, and asking whether you need to.
_LECTURER_PUBLIC_PATHS = {"/api/lecturer/login", "/api/lecturer/logout", "/api/lecturer/session"}


@app.middleware("http")
async def lecturer_auth(request: Request, call_next):
    """Every /api/lecturer/* route is the lecturer's only (see backend/auth.py):
    it exposes students' code, reference solutions and hidden tests, and runs
    the lecture. Checked here once, so a new lecturer route can't forget it."""
    path = request.scope["path"]
    if (
        path.startswith("/api/lecturer/")
        and path not in _LECTURER_PUBLIC_PATHS
        and not auth.is_lecturer(request.cookies.get(auth.COOKIE_NAME), request.headers.get(auth.HEADER_NAME))
    ):
        return JSONResponse({"detail": "Log in as the lecturer first."}, status_code=401)
    return await call_next(request)


@app.on_event("startup")
def startup():
    store.init_db()
    if not auth.auth_required():
        logging.getLogger("uvicorn.error").warning(
            "LECTURER_PASSWORD is not set: the lecturer pages and API are open to anyone who can reach this "
            "server. Fine for local development; set it before students can connect."
        )


class LecturerLoginRequest(BaseModel):
    password: str


@app.get("/api/lecturer/session")
def api_lecturer_session(request: Request):
    """What the lecturer pages check before showing anything: whether a login
    is needed at all, and whether this browser has one."""
    return {
        "auth_required": auth.auth_required(),
        "logged_in": auth.is_lecturer(request.cookies.get(auth.COOKIE_NAME), request.headers.get(auth.HEADER_NAME)),
    }


@app.post("/api/lecturer/login")
async def api_lecturer_login(req: LecturerLoginRequest, request: Request, response: Response):
    if not auth.auth_required():
        return {"logged_in": True}
    if not auth.password_matches(req.password):
        await anyio.sleep(1)  # makes guessing slow, without holding a thread
        raise HTTPException(status_code=401, detail="That password isn't right.")
    response.set_cookie(
        auth.COOKIE_NAME,
        auth.new_session_cookie(),
        max_age=auth.SESSION_SECONDS,
        httponly=True,
        samesite="strict",
        # Behind an HTTPS proxy this needs uvicorn's --proxy-headers to see "https".
        secure=request.url.scheme == "https",
    )
    return {"logged_in": True}


@app.post("/api/lecturer/logout")
def api_lecturer_logout(response: Response):
    response.delete_cookie(auth.COOKIE_NAME)
    return {"logged_in": False}


# Student requests don't say who the student is: that comes from their join
# token (the X-Student-Token header, see _student), never from a typed name.
class SubmitRequest(BaseModel):
    question_id: str
    source_code: str


class RunRequest(BaseModel):
    # "Run" on the student page: one ungraded run with stdin the student chose.
    question_id: str
    source_code: str
    stdin: str = ""


class TestFile(BaseModel):
    # A data file the student's program opens by name -- see backend/test_files.py.
    name: str
    content: str


class TestCase(BaseModel):
    stdin: str
    expected_stdout: str
    files: list[TestFile] = []


class QuestionCreateRequest(BaseModel):
    title: str
    prompt: str
    language: str = "python"
    test_cases: list[TestCase]
    reference_solution: str | None = None
    cpu_time_limit_s: float = 5
    memory_limit_kb: int = 128000
    extra_packages: list[str] = []
    line_limit: int = DEFAULT_LINE_LIMIT
    expected_students: int | None = None
    duration_seconds: int = 600
    idle_nudge_seconds: int = 180
    # Grade what the program writes to this file (e.g. "result.txt") instead of
    # what it prints; None = printed output, as before.
    output_file: str | None = None
    # What students start with in their editor; None = the student page's
    # default for the language. See store.py's starter_code column.
    starter_code: str | None = None
    # The task's own wrong-answer hints, attempt 1 first; None = generic hints.
    # See backend/hint_ladder.py.
    hint_ladder: list[str] | None = None


class QuestionUpdateRequest(BaseModel):
    # Same shape as create, all optional -- only fields actually sent are
    # changed (see api_lecturer_update_question). Only allowed while draft.
    title: str | None = None
    prompt: str | None = None
    language: str | None = None
    test_cases: list[TestCase] | None = None
    reference_solution: str | None = None
    cpu_time_limit_s: float | None = None
    memory_limit_kb: int | None = None
    extra_packages: list[str] | None = None
    line_limit: int | None = None
    expected_students: int | None = None
    duration_seconds: int | None = None
    idle_nudge_seconds: int | None = None
    output_file: str | None = None
    starter_code: str | None = None
    # The task's own wrong-answer hints, attempt 1 first; None = generic hints.
    # See backend/hint_ladder.py.
    hint_ladder: list[str] | None = None


class LectureAdvanceRequest(BaseModel):
    # The dashboard's own question_id, so "Next task"/"Finish lecture" can
    # close it out even if it somehow isn't the most-recently-started live
    # question (see api_lecturer_lecture_next/finish).
    current_question_id: str | None = None


class HintDraftRequest(BaseModel):
    # The form as it is now -- the draft doesn't need the question saved first.
    prompt: str
    language: str = "python"
    reference_solution: str
    starter_code: str | None = None


class LectureCreateRequest(BaseModel):
    label: str | None = None


class RaiseIssueRequest(BaseModel):
    # Identifies one cluster from GET /api/lecturer/clusters -- its own
    # exec_verdict/error_type plus its submission_ids.
    question_id: str
    exec_verdict: str
    error_type: str | None = None
    submission_ids: list[int]
    raised: bool = True
    # The snippet to put on screen (one of submission_ids); defaults to the
    # first. See aggregation.raise_issue().
    example_submission_id: int | None = None


class ShowSubmissionRequest(BaseModel):
    shown: bool = True


class MoveQueueEntryRequest(BaseModel):
    # The entry's new place in the queue, 0-based (clamped to the queue).
    index: int


class ScreenQueueCurrentRequest(BaseModel):
    # Either jump to one entry, or move `step` places along the queue
    # (the projector's Previous/Next: -1/+1).
    entry_id: int | None = None
    step: int | None = None


class LectureJoinRequest(BaseModel):
    code: str
    student_name: str = Field(max_length=60)
    # This browser's token from an earlier join of the same lecture, if any --
    # lets a student rejoin under their own name (see store.join_student).
    token: str | None = None


class ActivityRequest(BaseModel):
    question_id: str
    # Whether the student typed anything since their previous heartbeat --
    # never the code itself.
    edited: bool = False


@app.get("/api/questions")
def api_list_questions():
    return list_questions()


@app.get("/api/lecturer/questions")
def api_lecturer_list_questions():
    """The setup page's question list -- scoped to never-started drafts plus
    whatever's tied to the currently active lecture, not every question ever
    authored (see store.list_question_rows()'s docstring)."""
    return store.list_question_rows(current_lecture_only=True)


@app.post("/api/lecturer/questions")
def api_lecturer_create_question(req: QuestionCreateRequest):
    fields = req.model_dump()
    fields["test_cases"] = [tc.model_dump() for tc in req.test_cases]
    fields["output_file"] = (fields.get("output_file") or "").strip() or None
    fields["hint_ladder"] = clean_ladder(fields.get("hint_ladder"))
    _check_test_files_or_400(fields["test_cases"], fields["output_file"])
    question_id = store.create_question(fields)
    return store.get_question_row(question_id)


@app.get("/api/lecturer/questions/{question_id}")
def api_lecturer_question_detail(question_id: str, include_files: bool = False):
    """The live dashboard polls this every 3 s, so test files come back as name
    and size only unless include_files=true (up to 1 MB each -- see
    backend/test_files.py)."""
    row = store.get_question_row(question_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    if not include_files:
        row["test_cases"] = test_files.without_contents(row["test_cases"])
    return row


def _check_test_files_or_400(test_cases: list, output_file: str | None) -> None:
    problem = test_files.check_test_files(test_cases) or test_files.check_output_file(output_file, test_cases)
    if problem:
        raise HTTPException(status_code=400, detail=problem)


# Question fields the validation preview depends on -- see
# api_lecturer_update_question.
_VALIDATION_FIELDS = (
    "test_cases", "reference_solution", "language",
    "cpu_time_limit_s", "memory_limit_kb", "extra_packages", "line_limit", "output_file",
    # The check also looks at the starter (see _starter_problem).
    "starter_code",
)


@app.put("/api/lecturer/questions/{question_id}")
def api_lecturer_update_question(question_id: str, req: QuestionUpdateRequest):
    row = store.get_question_row(question_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    if row["status"] != "draft":
        raise HTTPException(status_code=409, detail="Cannot edit a question once it has started.")

    # exclude_unset (not "v is not None") so a field explicitly sent as null
    # -- e.g. clearing reference_solution or expected_students -- actually
    # clears it, while a field the client never sent at all still leaves the
    # existing value alone.
    fields = req.model_dump(exclude_unset=True)
    if "test_cases" in fields:
        fields["test_cases"] = [tc if isinstance(tc, dict) else tc.model_dump() for tc in req.test_cases]
    if "output_file" in fields:
        fields["output_file"] = (fields["output_file"] or "").strip() or None
    if "hint_ladder" in fields:
        fields["hint_ladder"] = clean_ladder(fields["hint_ladder"])
    if "test_cases" in fields or "output_file" in fields:
        _check_test_files_or_400(
            fields.get("test_cases", row["test_cases"]), fields.get("output_file", row.get("output_file"))
        )
    # NOT NULL column -- "off" is 0, not null.
    if "idle_nudge_seconds" in fields and fields["idle_nudge_seconds"] is None:
        del fields["idle_nudge_seconds"]
    if fields:
        # Only a change that can alter the validation result (running the
        # reference solution against the tests under these limits) throws it
        # away -- editing the title, task text, timing or class size can't, and
        # un-validating on those made the setup page's "Save" after a passing
        # check flip the question back to "needs a check".
        if any(field in fields and fields[field] != row[field] for field in _VALIDATION_FIELDS):
            fields["validated"] = 0
        store.update_question(question_id, fields)
    return store.get_question_row(question_id)


@app.post("/api/lecturer/hints/draft")
def api_lecturer_draft_hints(req: HintDraftRequest):
    """Drafts the task's wrong-answer hint ladder for the lecturer to edit. Saves
    nothing: the hints only reach students once the lecturer saves them with the
    question (hint_ladder). A slow model call, so it runs off the event loop
    like the other blocking calls here."""
    if not req.prompt.strip() or not req.reference_solution.strip():
        raise HTTPException(status_code=400, detail="Write the task text and a reference solution first.")
    try:
        hints = draft_hint_ladder(req.prompt, req.language, req.reference_solution, req.starter_code)
    except RuntimeError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"hints": hints}


@app.delete("/api/lecturer/questions/{question_id}")
def api_lecturer_delete_question(question_id: str):
    """Removes a draft question outright -- the setup page's delete button.
    Same status rule as editing: once a question has gone live, its history
    needs to stay put for the session summary/recap, so this only ever
    touches drafts."""
    row = store.get_question_row(question_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    if row["status"] != "draft":
        raise HTTPException(status_code=409, detail="Cannot delete a question once it has started.")
    store.delete_question(question_id)
    return {"deleted": True}


@app.post("/api/lecturer/questions/{question_id}/validate")
def api_lecturer_validate_question(question_id: str):
    """Runs the question's own rubric against its reference solution -- the
    cheap-insurance preview step from landing-page-scoping-decision.md, so a
    broken test case doesn't surface live in front of the class. Marks the
    question validated (a prerequisite for /start) only if every test case
    passes."""
    question = store.get_question_row(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Not found")
    if not question.get("reference_solution"):
        raise HTTPException(
            status_code=400, detail="Add a reference (known-correct) solution before validating."
        )
    if len(question["test_cases"]) < 2:
        # The first test is shown to students and doesn't count towards the
        # verdict (see _graded), so at least one more is needed to grade on.
        raise HTTPException(
            status_code=400,
            detail="Add at least 2 test cases. The first is shown to students, so it isn't graded.",
        )

    try:
        results = run_test_cases(
            question["reference_solution"],
            question["test_cases"],
            language=question["language"],
            cpu_time_limit=question["cpu_time_limit_s"],
            memory_limit_kb=question["memory_limit_kb"],
            output_file=question.get("output_file"),
        )
    except Judge0Error as e:
        raise HTTPException(status_code=502, detail=str(e))

    try:
        starter_problem = _starter_problem(question)
    except Judge0Error as e:
        raise HTTPException(status_code=502, detail=str(e))

    all_passed = bool(results) and all(r["passed"] for r in results)
    validated = all_passed and not (starter_problem and starter_problem["blocking"])
    store.set_validated(question_id, validated)
    return {"validated": validated, "results": results, "starter_problem": starter_problem}


def _starter_problem(question: dict) -> dict | None:
    """What's wrong with the lecturer's starter code, if anything: None, or
    {"blocking": bool, "message": str} for the setup page to show.

    Blocking (the task can't go live): the starter alone already breaks a
    submission rule -- longer than the line limit, or importing a package that
    isn't allowed -- so every student who keeps it would be rejected before
    their code even runs.

    Not blocking: the starter doesn't run as it is on the example test (a typo
    in a helper function, say). Only a heads-up, because a skeleton students
    are meant to complete legitimately doesn't run yet.

    Only the lecturer's own starter is checked; the built-in defaults are known
    to be fine."""
    starter = question.get("starter_code")
    if not starter or not starter.strip():
        return None

    reason = pre_execution_check(
        starter, line_limit=question["line_limit"], extra_packages=question["extra_packages"],
        language=question["language"],
    )
    if reason == "too_long":
        return {
            "blocking": True,
            "message": (
                f"The starter code is {starter.count(chr(10)) + 1} lines, over this task's line limit of "
                f"{question['line_limit']}, so every submission would be rejected. Shorten it, or raise the line limit."
            ),
        }
    if reason == "disallowed_package":
        return {
            "blocking": True,
            "message": (
                "The starter code imports a package students aren't allowed to use, so every submission that keeps "
                "it would be rejected. Add the package to the allowed packages, or remove the import."
            ),
        }
    if reason:
        return {"blocking": True, "message": f"The starter code can't be submitted as it is ({reason.replace('_', ' ')})."}

    example = question["test_cases"][0]
    r = run_submission(
        starter,
        example["stdin"],
        language=question["language"],
        cpu_time_limit=question["cpu_time_limit_s"],
        memory_limit_kb=question["memory_limit_kb"],
        files=test_files.files_of(example) or None,
        output_file=question.get("output_file"),
    )
    if r["status_description"] == "Accepted":
        return None
    return {
        "blocking": False,
        "message": (
            f"The starter code doesn't run as it is ({_error_summary(r)}). "
            "That's fine if students are meant to complete it."
        ),
    }


def _error_summary(result: dict) -> str:
    """One line saying why a run failed: the compiler's first error line, else
    the last line of the program's error output, else Judge0's status."""
    compile_output = (result.get("compile_output") or "").strip()
    if compile_output:
        lines = [l.strip() for l in compile_output.splitlines() if l.strip()]
        line = next((l for l in lines if "error" in l.lower()), lines[-1])
    else:
        stderr_lines = [l.strip() for l in (result.get("stderr") or "").splitlines() if l.strip()]
        line = stderr_lines[-1] if stderr_lines else (result.get("status_description") or "it failed")
    return line if len(line) <= 200 else line[:197] + "..."


@app.post("/api/lecturer/questions/{question_id}/start")
def api_lecturer_start_question(question_id: str):
    """Flips a question from draft into live -- the boundary where the live
    lecturer-dashboard view (submission progress, verdict breakdown,
    discussion points) takes over. Requires the validation preview to have
    passed first."""
    question = store.get_question_row(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Not found")
    if question["status"] == "live":
        return question
    if not question["validated"]:
        raise HTTPException(
            status_code=400,
            detail="Run the validation preview against a reference solution before starting.",
        )
    try:
        store.start_question(question_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return store.get_question_row(question_id)


@app.post("/api/lecturer/questions/{question_id}/close")
def api_lecturer_close_question(question_id: str):
    """Ends a question's live window without starting another -- used
    standalone, and internally by the "Next task"/"Finish lecture" flow
    below, whenever the dashboard's current question needs to stop accepting
    submissions."""
    question = store.get_question_row(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Not found")
    if question["status"] == "live":
        store.close_question(question_id)
    return store.get_question_row(question_id)


@app.post("/api/lecturer/questions/{question_id}/end_now")
def api_lecturer_end_question_now(question_id: str):
    """The live dashboard's "End task now" -- e.g. everyone has already
    answered. Puts the task straight into its "time's up" state (see
    store.end_question_now()) rather than closing it or starting the next
    one, so the lecturer can still go over results and show examples."""
    question = store.get_question_row(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Not found")
    if question["status"] != "live":
        raise HTTPException(status_code=409, detail="This task isn't live.")
    store.end_question_now(question_id)
    return store.get_question_row(question_id)


@app.get("/api/lecturer/questions/{question_id}/shown_submissions")
def api_lecturer_shown_submissions(question_id: str):
    """Ids of the single submissions the lecturer is showing the class (see
    api_lecturer_show_submission) -- for the drawer's button state."""
    return store.shown_submission_ids(question_id, single_only=True)


@app.post("/api/lecturer/submissions/{submission_id}/show")
def api_lecturer_show_submission(submission_id: int, req: ShowSubmissionRequest):
    """"Add to queue" in a student's code drawer on the live dashboard: adds
    that one attempt -- any verdict, a correct solution included -- to the
    end of the screen queue (or takes it out). No name is shown. Only the
    projector moves what's on screen (2026-11-18), so this never jumps the
    class to it, even after time is up. Returns the question's shown
    single-submission ids."""
    sub = store.get_submission(submission_id)
    if not sub:
        raise HTTPException(status_code=404, detail="Not found")
    store.set_submission_shown(sub, req.shown)
    return store.shown_submission_ids(sub["question_id"], single_only=True)


# The screen queue: everything the lecturer has lined up to show the class
# (raised discussion points' examples and single attempts), in order. Queued
# while the task runs; once time is up the projector and students' waiting
# screens show one entry at a time and the projector steps through them
# (screen_queue/current -- the lecturer dashboard only queues, reorders and
# removes). Each call returns the queue as aggregation.screen_queue() describes it.
@app.get("/api/lecturer/questions/{question_id}/screen_queue")
def api_lecturer_screen_queue(question_id: str):
    return screen_queue(question_id)


@app.post("/api/lecturer/screen_queue/{entry_id}/move")
def api_lecturer_move_queue_entry(entry_id: int, req: MoveQueueEntryRequest):
    entry = store.get_queue_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Not found")
    store.move_queue_entry(entry_id, req.index)
    return screen_queue(entry["question_id"])


@app.delete("/api/lecturer/screen_queue/{entry_id}")
def api_lecturer_delete_queue_entry(entry_id: int):
    entry = store.get_queue_entry(entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Not found")
    store.delete_queue_entry(entry_id)
    return screen_queue(entry["question_id"])


@app.post("/api/lecturer/questions/{question_id}/screen_queue/current")
def api_lecturer_set_screen_queue_current(question_id: str, req: ScreenQueueCurrentRequest):
    if req.entry_id is not None:
        entry = store.get_queue_entry(req.entry_id)
        if not entry or entry["question_id"] != question_id:
            raise HTTPException(status_code=404, detail="Not found")
        store.set_current_queue_entry(question_id, req.entry_id)
    elif req.step is not None:
        store.step_current_queue_entry(question_id, req.step)
    else:
        raise HTTPException(status_code=400, detail="Give entry_id or step.")
    return screen_queue(question_id)


@app.post("/api/lecturer/lectures")
def api_lecturer_create_lecture(req: LectureCreateRequest):
    """The home dashboard's "New lecture" action -- the only place a lecture
    now starts (see store.start_question()'s docstring). 409s if one is
    already in progress; the dashboard is expected to offer "Resume live
    lecture" instead in that case."""
    try:
        return store.create_lecture(req.label)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))


@app.get("/api/lecturer/lectures/active")
def api_lecturer_active_lecture():
    """What the home dashboard checks to decide "New lecture" vs. "Resume
    live lecture", and -- via live_question_id -- whether resuming should
    land on the live task dashboard or back in task setup (a lecture can be
    active with no question currently live, e.g. right after creation or
    between "Next task" clicks with no drafts left). has_next_task is whether
    "Next task" would start anything (see api_lecturer_lecture_next) -- the
    live dashboard swaps that button for "End lecture" once it wouldn't."""
    lecture = store.get_active_lecture()
    if not lecture:
        return {"lecture": None, "live_question_id": None}
    live_question = store.live_question_row()
    # "Task N of M" on the live dashboard: tasks run so far (incl. the live
    # one) plus the drafts still to come.
    ran = [q["id"] for q in store.questions_for_lecture(lecture["id"])]
    task_number = ran.index(live_question["id"]) + 1 if live_question and live_question["id"] in ran else None
    return {
        "lecture": lecture,
        "live_question_id": live_question["id"] if live_question else None,
        "has_next_task": store.next_draft_question() is not None,
        "task_number": task_number,
        "task_count": len(ran) + store.count_ready_drafts(),
    }


@app.get("/api/lecturer/lectures/review")
def api_lecturer_lecture_review(include_archived: bool = False):
    """Declared before /lectures/{lecture_id} so "review" isn't read as an id.

    Finished lectures ranked by how many students solved their tasks, worst
    first, with each lecture's weakest tasks and their most common issue -- the
    history page's "Needs revisiting" view. See aggregation.lecture_review()."""
    return lecture_review(include_archived=include_archived)


@app.get("/api/lecturer/lectures/{lecture_id}")
def api_lecturer_lecture_detail(lecture_id: int):
    lecture = store.get_lecture_row(lecture_id)
    if not lecture:
        raise HTTPException(status_code=404, detail="Not found")
    return lecture


@app.post("/api/lecturer/lectures/{lecture_id}/open_lobby")
def api_lecturer_open_lobby(lecture_id: int):
    """Opens the lobby: from here on the join code is live and students can
    actually join (see api_lecture_join below) and the first question can be
    started (see store.start_question()'s docstring) -- setup.html's "Open
    lobby" button. Idempotent (store.open_lobby()'s docstring), so this is
    also what a lecturer navigating back into the lobby view resolves to."""
    lecture = store.get_lecture_row(lecture_id)
    if not lecture:
        raise HTTPException(status_code=404, detail="Not found")
    if lecture["ended_at"]:
        raise HTTPException(status_code=409, detail="This lecture has already ended.")
    return store.open_lobby(lecture_id)


@app.get("/api/lecturer/lectures/{lecture_id}/joined_count")
def api_lecturer_joined_count(lecture_id: int):
    """The lobby view's live "N joined" counter."""
    return {"joined": store.joined_count(lecture_id)}


@app.get("/api/lecturer/lectures")
def api_lecturer_list_lectures(include_archived: bool = False):
    """Lecture history for the home dashboard -- excludes archived (junk/
    test) lectures by default."""
    return store.list_lectures(include_archived=include_archived)


@app.post("/api/lecturer/lectures/{lecture_id}/archive")
def api_lecturer_archive_lecture(lecture_id: int):
    """Hides a lecture from the default history list without deleting its
    data -- see store.set_lecture_archived()'s docstring."""
    if not store.get_lecture_row(lecture_id):
        raise HTTPException(status_code=404, detail="Not found")
    store.set_lecture_archived(lecture_id, True)
    return store.get_lecture_row(lecture_id)


@app.post("/api/lecturer/lectures/{lecture_id}/unarchive")
def api_lecturer_unarchive_lecture(lecture_id: int):
    if not store.get_lecture_row(lecture_id):
        raise HTTPException(status_code=404, detail="Not found")
    store.set_lecture_archived(lecture_id, False)
    return store.get_lecture_row(lecture_id)


@app.delete("/api/lecturer/lectures/{lecture_id}")
def api_lecturer_delete_lecture(lecture_id: int):
    """Removes a lecture outright, for "created it, changed my mind before
    starting it" -- distinct from archive, which is for a lecture that DID
    happen and you just want out of the default view. Refused once any
    question has gone live under it (same status-based rule delete_question
    uses): at that point there's real history worth keeping, and archive is
    the right tool instead."""
    if not store.get_lecture_row(lecture_id):
        raise HTTPException(status_code=404, detail="Not found")
    if store.questions_for_lecture(lecture_id):
        raise HTTPException(
            status_code=409,
            detail="Cannot delete a lecture once a question has started. Archive it instead.",
        )
    store.delete_lecture(lecture_id)
    return {"deleted": True}


@app.get("/api/lecturer/stats/totals")
def api_lecturer_totals():
    """All-time totals line on the home dashboard: lectures run + total
    submissions, across the whole history (archived included)."""
    return store.lecture_totals()


@app.post("/api/lecturer/lecture/next")
def api_lecturer_lecture_next(req: LectureAdvanceRequest):
    """Closes the dashboard's current question (if it's still live) and
    starts the next validated draft question, in creation order -- the
    "Next task" button. Returns {"started": null} when there's nothing left
    to advance to, so the lecturer knows to use "Finish lecture" instead.

    409s when the dashboard isn't on the live task (a past lecture's task,
    or an earlier one in this lecture): "Next task" from there would start
    the *active* lecture's next draft from a page about something else."""
    if req.current_question_id:
        current = store.get_question_row(req.current_question_id)
        if not current:
            raise HTTPException(status_code=404, detail="Not found")
        if current["status"] != "live":
            raise HTTPException(status_code=409, detail="This task has already finished, so it can't move the lecture on.")
        store.close_question(req.current_question_id)

    next_question = store.next_draft_question()
    if not next_question:
        return {"started": None}

    try:
        store.start_question(next_question["id"])
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"started": store.get_question_row(next_question["id"])}


@app.post("/api/lecturer/lecture/finish")
def api_lecturer_lecture_finish(req: LectureAdvanceRequest):
    """Closes the dashboard's current question (if it's still live) and ends
    the active lecture -- the "Finish lecture"/"End session" button. Distinct
    from just running out of draft questions: the lecturer can end early
    even with drafts left unstarted. Returns the ended lecture's id so the
    caller can link straight to its (now generalized) summary view.

    409s when the dashboard's task belongs to a different lecture than the
    active one -- ending the lecture from an old lecture's page would end
    whatever lecture is running now."""
    lecture = store.get_active_lecture()
    if req.current_question_id:
        current = store.get_question_row(req.current_question_id)
        if not current:
            raise HTTPException(status_code=404, detail="Not found")
        if not lecture or current.get("lecture_id") != lecture["id"]:
            raise HTTPException(status_code=409, detail="This task is from a lecture that has already ended.")
        if current["status"] == "live":
            store.close_question(req.current_question_id)

    if lecture:
        store.end_lecture(lecture["id"])
    return {"finished": True, "lecture_id": lecture["id"] if lecture else None}


@app.get("/api/lecturer/lecture/summary")
def api_lecturer_lecture_summary(lecture_id: int | None = None):
    """The STATE 2 post-lecture view: per-task submission rate + verdict
    trend across every task in the lecture, plus carry-forward discussion
    points (issues that recurred across 2+ tasks). Defaults to the current
    lecture -- see store.current_lecture_row()'s docstring for why that
    stays correct right after "End session" without the caller having to
    pass anything. Also reachable directly via ?lecture_id= from the home
    dashboard's history list, for any past lecture, not just the most
    recent one."""
    if lecture_id is None:
        current = store.current_lecture_row()
        if not current:
            raise HTTPException(status_code=404, detail="No lecture has been run yet.")
        lecture_id = current["id"]
    lecture = store.get_lecture_row(lecture_id)
    if not lecture:
        raise HTTPException(status_code=404, detail="Not found")
    return {
        "lecture_id": lecture_id,
        "lecture_label": lecture["display_label"],
        "tasks": session_summary(lecture_id),
        "carry_forward_discussion_points": carry_forward_discussion_points(lecture_id),
    }


def _student(x_student_token: str | None = Header(default=None)) -> dict:
    """Who's asking, from the token their join handed out (see
    api_lecture_join): {"lecture_id", "student_name"}. 401 without a valid one --
    the student page sends the student back to the join screen."""
    student = store.student_for_token(x_student_token) if x_student_token else None
    if not student:
        raise HTTPException(status_code=401, detail="You're not in this lecture. Join it again with the lecture code.")
    return student


def _check_student_question(student: dict, question: dict) -> None:
    """A student's token only works for their own lecture's tasks."""
    if question.get("lecture_id") != student["lecture_id"]:
        raise HTTPException(status_code=403, detail="This task belongs to a different lecture.")


@app.get("/api/lecture/recap")
def api_lecture_recap(student: dict = Depends(_student)):
    """The STATE 2 student recap: this student's own attempted-vs-total and
    per-task verdicts for the lecture they joined. No class-wide comparison --
    see student_recap()'s docstring."""
    return student_recap(student["lecture_id"], student["student_name"])


def _seconds_remaining(question: dict) -> int:
    if not question.get("started_at"):
        return question["duration_seconds"]
    started = datetime.strptime(question["started_at"], "%Y-%m-%d %H:%M:%S")
    elapsed = (datetime.utcnow() - started).total_seconds()
    return max(0, int(question["duration_seconds"] - elapsed))


@app.get("/api/lecture/status")
def api_lecture_status():
    """Polled by the student page (see live-submission-progress-decision-
    style reasoning in student/App.tsx) to find the currently live question,
    its timer, and whether the lecturer has ended the lecture -- so a
    student's browser can auto-switch to a new task or the "waiting"/
    "finished" screen without a manual reload."""
    question = store.live_question_row()
    current_lecture = store.current_lecture_row()
    finished = bool(current_lecture and current_lecture["ended_at"])
    # Which lecture this status is about -- the student page compares it to
    # the lecture it joined, so a tab left open (or refreshed) after the
    # lecturer starts a *new* lecture is sent back to the join screen instead
    # of silently carrying the old join over.
    lecture_id = current_lecture["id"] if current_lecture else None
    if not question:
        return {"finished": finished, "lecture_id": lecture_id, "question": None, "shown_examples": [], "shown_position": None}

    tests = test_files.without_contents(question["test_cases"])
    time_up = _seconds_remaining(question) <= 0
    return {
        "finished": finished,
        "lecture_id": lecture_id,
        "question": {
            "id": question["id"],
            # Its place in this lecture ("Task 2"), in run order; None if it
            # isn't tied to a lecture.
            "number": _task_number(question),
            "title": question["title"],
            "prompt": question["prompt"],
            "language": question["language"],
            "example": tests[0] if tests else None,
            # Grade what the program writes to this file instead of what it prints.
            "output_file": question.get("output_file"),
            # The lecturer's own starter code; None = the student page's default.
            "starter_code": question.get("starter_code"),
            # Data files the student may open in the viewer (name and size; the
            # content comes from api_lecture_test_file): the example's while the
            # task runs, every test's once time is up.
            "files": [
                {"test": i, **meta}
                for i, case in enumerate(tests)
                if _test_files_visible(question, i)
                for meta in case["files"]
            ],
            "duration_seconds": question["duration_seconds"],
            "started_at": question["started_at"],
            "seconds_remaining": _seconds_remaining(question),
        },
        # What the lecturer is showing the class: the screen queue's current
        # entry (aggregation.shown_examples()) -- only once time is up, so no
        # student sees anyone else's attempt while they're still answering.
        "shown_examples": shown_examples(question["id"]) if time_up else [],
        # Where that entry sits in the queue, for the projector's
        # Previous/Next controls; None before time is up or with nothing queued.
        "shown_position": screen_position(question["id"]) if time_up else None,
    }


def _task_number(question: dict) -> int | None:
    lecture_id = question.get("lecture_id")
    if lecture_id is None:
        return None
    ids = [q["id"] for q in store.questions_for_lecture(lecture_id)]
    return ids.index(question["id"]) + 1 if question["id"] in ids else None


def _test_files_visible(question: dict, test_index: int) -> bool:
    """The example's files always; a graded test's only once students can no
    longer submit (time's up, or the task was closed) -- see backend/test_files.py."""
    if test_index == 0:
        return True
    return question["status"] != "live" or _seconds_remaining(question) <= 0


@app.get("/api/lecture/questions/{question_id}/tests/{test_index}/files/{name:path}")
def api_lecture_test_file(question_id: str, test_index: int, name: str):
    """One test file's content, for the student page's file viewer. Same
    visibility rule as the status endpoint's `files` list."""
    question = store.get_question_row(question_id)
    if (
        not question
        or question["status"] not in ("live", "closed")  # never-run drafts/skipped tasks stay private
        or not 0 <= test_index < len(question["test_cases"])
    ):
        raise HTTPException(status_code=404, detail="Not found")
    match = next((f for f in test_files.files_of(question["test_cases"][test_index]) if f["name"] == name), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Not found")
    if not _test_files_visible(question, test_index):
        raise HTTPException(status_code=403, detail="This test's files are shown once the task is over.")
    return PlainTextResponse(match["content"])


@app.get("/api/lecture/attempts")
def api_lecture_attempts(question_id: str, student: dict = Depends(_student)):
    """The asking student's own attempts at a question, for the student page's
    "Your attempts" trail. Only what that trail shows: the student page used to
    read the lecturer's submissions feed for this, which handed every student
    every classmate's code and every hidden test's input, expected output and
    program output."""
    question = store.get_question_row(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Not found")
    _check_student_question(student, question)
    name = student["student_name"]
    return [
        {
            "id": row["id"],
            "attempt_number": row["attempt_number"],
            "verdict": row["verdict"],
            "tests_passed": row["tests_passed"],
            "tests_total": row["tests_total"],
            "created_at": row["created_at"],
        }
        for row in store.all_submissions(question_id)
        if row["student_name"] == name
    ]


@app.post("/api/lecture/join")
def api_lecture_join(req: LectureJoinRequest):
    """Kahoot-style entry gate for the student page (store.check_join_code's
    docstring) -- called once, before the student page starts polling
    /api/lecture/status. The right code gets the student a token (see
    store.join_student()) that every student request after this carries, so
    submitting, running code and the heartbeat need the code too, and nobody
    can act under a classmate's name. Also backs the lobby's live "N joined"
    counter.

    A name already used in this lecture is refused (409), except for the
    browser that holds its token -- a refresh or reopened tab rejoins as the
    same student."""
    active = store.get_active_lecture()
    if not active:
        raise HTTPException(status_code=404, detail="No lecture is live right now.")
    if not active.get("lobby_opened_at"):
        raise HTTPException(
            status_code=403, detail="This lecture hasn't been opened for joining yet. Check with your lecturer."
        )
    lecture = store.check_join_code(req.code)
    if not lecture:
        raise HTTPException(status_code=403, detail="That code didn't match. Check with your lecturer and try again.")
    student_name = req.student_name.strip()
    if not student_name:
        raise HTTPException(status_code=400, detail="Enter your name.")
    try:
        identity = store.join_student(lecture["id"], student_name, req.token)
    except store.NameTaken:
        raise HTTPException(
            status_code=409,
            detail="Someone in this lecture already joined with that name. Add your last initial, e.g. \"Ola N.\".",
        )
    return {
        "lecture_id": lecture["id"],
        "label": lecture["display_label"],
        "student_name": identity["student_name"],
        "token": identity["token"],
    }


# The student page sends a heartbeat this often while a task is running (see
# HEARTBEAT_MS in student/App.tsx); a student is "away" once a few in a row
# have gone missing (tab closed, laptop asleep, network gone).
AWAY_AFTER_SECONDS = 30

# Used for the lecturer's idle status when a question has nudges turned off
# (idle_nudge_seconds = 0) -- "idle" still means something to the lecturer
# even if the student isn't being nudged.
DEFAULT_IDLE_SECONDS = 180

# The automatic idle nudge. Deliberately generic: it has to be safe for any
# task and any student, so it only points at first steps (tier-0 scaffolds in
# hint-taxonomy-draft.md terms) and never at the answer.
IDLE_NUDGE_MESSAGE = (
    "Still with us? It's been a little while since you last typed. "
    "A small first step helps: work through the example by hand, or write just the part "
    "that reads the input and submit it to see which tests pass. "
    "Stuck? Put your hand up, that's what the lecturer is here for."
)


def _seconds_since(sqlite_ts: str) -> float:
    then = datetime.strptime(sqlite_ts, "%Y-%m-%d %H:%M:%S")
    return (datetime.utcnow() - then).total_seconds()


@app.post("/api/lecture/activity")
def api_lecture_activity(req: ActivityRequest, student: dict = Depends(_student)):
    """Heartbeat from the student editor while a task runs (see class-
    progress-visualization-decision.md). Records only whether the student
    typed since their last heartbeat, and answers with a nudge when they've
    been idle past the question's idle_nudge_seconds -- once per idle
    stretch (typing resets it), never after time's up, never once they've
    solved it."""
    student_name = student["student_name"]
    question = store.get_question_row(req.question_id)
    if (
        not question
        or question.get("lecture_id") != student["lecture_id"]
        or question["status"] != "live"
        or _seconds_remaining(question) <= 0
    ):
        return {"nudge": None}
    row = store.record_activity(req.question_id, student_name, req.edited)
    threshold = question["idle_nudge_seconds"]
    idle_for = _seconds_since(row["last_edit_at"] or row["first_seen_at"])
    if (
        threshold > 0
        and idle_for >= threshold
        and row["nudged_at"] is None
        and not store.has_solved(req.question_id, student_name)
    ):
        store.mark_nudged(req.question_id, student_name)
        return {"nudge": IDLE_NUDGE_MESSAGE}
    return {"nudge": None}


# Shown to a student whose program ran but never created the task's output file.
MISSING_OUTPUT_FILE_FEEDBACK = (
    "Your program ran, but it didn't create {name}. This task checks what your program "
    'writes to {name}, not what it prints. Write your answer to it, e.g. with open("{name}", "w").'
)

# Shown to a student whose program never reads its input (see api_submit).
IGNORES_INPUT_FEEDBACK = (
    "Your program never reads the input, so it gives the same answer every time. "
    "Work the answer out from the input: read it with input(), or use what the starter code already read for you."
)


def _graded(test_results: list) -> list:
    """The test results that decide a submission's verdict: every test except
    the first, which students see as the worked example -- otherwise printing
    the example's answer passes it (print(6) for "1 2 3" -> 6). A question with a
    single test has nothing else to grade on, so that test counts; validation
    now requires a second test for new questions."""
    return test_results[1:] if len(test_results) > 1 else test_results


# How many submissions are graded at once. Every other endpoint is a plain `def`,
# which FastAPI runs on a shared pool of 40 threads, and a submission holds its
# thread for the whole Judge0 run. Without this cap, a class submitting at once
# (time's up auto-submits everyone) took every thread, and the 2s status polls,
# heartbeats and lecturer dashboard queued behind grading: up to ~17s with 150
# students (load_test.py). Submissions over the cap wait here without holding a
# thread. Also caps concurrent requests to Judge0, which only has a few workers
# anyway, so a lower cap doesn't make grading itself slower.
MAX_CONCURRENT_SUBMITS = int(os.environ.get("MAX_CONCURRENT_SUBMITS", "16"))
_submit_limiter = anyio.CapacityLimiter(MAX_CONCURRENT_SUBMITS)


@app.post("/api/submit")
async def api_submit(req: SubmitRequest, student: dict = Depends(_student)):
    return await anyio.to_thread.run_sync(_submit, req, student, limiter=_submit_limiter)


def _submit(req: SubmitRequest, student: dict):
    question = get_question(req.question_id)
    if not question:
        raise HTTPException(status_code=404, detail=f"Unknown question_id: {req.question_id!r}")
    if question["status"] != "live":
        raise HTTPException(status_code=409, detail="This question isn't live (not started yet, or already closed).")
    _check_student_question(student, question)
    student_name = student["student_name"]

    # Submitting counts as working on it: reset the idle timer (and any nudge)
    # like typing does, so reading the feedback doesn't read as idle straight away.
    store.record_activity(req.question_id, student_name, edited=True)

    attempt_number = store.next_attempt_number(student_name, req.question_id)
    tests_total = len(_graded(question["test_cases"]))

    rejection_reason = pre_execution_check(
        req.source_code, line_limit=question["line_limit"], extra_packages=question["extra_packages"],
        language=question["language"],
    )
    if rejection_reason:
        # Rejected before ever reaching Judge0/Claude -- still recorded as a
        # real attempt, just tagged so it doesn't get mistaken for a graded one.
        sub_id = store.save_submission(
            {
                "student_name": student_name,
                "question_id": req.question_id,
                "language": question["language"],
                "source_code": req.source_code,
                "attempt_number": attempt_number,
                "tests_passed": 0,
                "tests_total": tests_total,
                "verdict": "error",
                "error_type": None,
                "exec_verdict": "rejected",
                "rejection_reason": rejection_reason,
                "feedback": f"Submission rejected before running: {rejection_reason}.",
                "discussion_point": None,
                "raw_test_results": json.dumps([]),
            }
        )
        return {
            "submission_id": sub_id,
            "tests_passed": 0,
            "tests_total": tests_total,
            "verdict": "error",
            "feedback": f"Your submission wasn't run: {rejection_reason}.",
        }

    try:
        test_results = run_test_cases(
            req.source_code,
            question["test_cases"],
            language=question["language"],
            cpu_time_limit=question["cpu_time_limit_s"],
            memory_limit_kb=question["memory_limit_kb"],
            output_file=question.get("output_file"),
        )
    except Judge0Error as e:
        # Judge0 itself is unreachable/broken -- distinct from the student's
        # code failing, which is a normal 200 response below.
        raise HTTPException(status_code=502, detail=str(e))

    try:
        feedback = judge_and_feedback(
            question["prompt"],
            req.source_code,
            _graded(test_results),
            language=question["language"],
            attempt_number=attempt_number,
            hint_ladder=question.get("hint_ladder"),
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI feedback failed: {e}")

    # Graded output file never created: the program ran fine but didn't write
    # the file the task asks for -- its own issue type, with feedback that says
    # so instead of a wrong-answer hint about output it never wrote.
    output_file = question.get("output_file")
    failing = next((r for r in _graded(test_results) if not r["passed"]), None)
    if (
        output_file
        and failing is not None
        and failing.get("output_file_missing")
        and failing["status_description"] == "Accepted"
    ):
        feedback.update(
            verdict="incorrect",
            exec_verdict="missing_output_file",
            error_type=None,
            feedback=MISSING_OUTPUT_FILE_FEEDBACK.format(name=output_file),
            hint_tier=None,
            hint_ceiling=None,
            traceback=None,
        )

    # Hard-coded output: a program that ran fine but never reads its input can
    # only pass by printing an expected answer it was given or guessed. Its own
    # issue type (not wrong_answer), so the lecturer sees it as one clear group.
    # Raw test results are stored unchanged.
    takes_input = any(tc["stdin"].strip() or test_files.files_of(tc) for tc in question["test_cases"])
    if (
        takes_input
        and feedback["exec_verdict"] in ("pass", "wrong_answer")
        and not reads_input(req.source_code, question["language"], question.get("starter_code"))
    ):
        feedback.update(
            verdict="incorrect",
            exec_verdict="ignores_input",
            error_type=None,
            feedback=IGNORES_INPUT_FEEDBACK,
            hint_tier=None,
            hint_ceiling=None,
            traceback=None,
        )

    sub_id = store.save_submission(
        {
            "student_name": student_name,
            "question_id": req.question_id,
            "language": question["language"],
            "source_code": req.source_code,
            "attempt_number": attempt_number,
            "tests_passed": feedback["tests_passed"],
            "tests_total": feedback["tests_total"],
            "verdict": feedback["verdict"],
            "error_type": feedback["error_type"],
            "exec_verdict": feedback["exec_verdict"],
            "rejection_reason": None,
            "feedback": feedback["feedback"],
            # Lecturer talking points are no longer per-submission -- they're computed
            # once per cluster of students who hit the same issue, on demand, by
            # aggregation.cluster_submissions(). Nothing to store per row.
            "discussion_point": None,
            "raw_test_results": json.dumps(test_results),
        }
    )

    return {
        "submission_id": sub_id,
        "tests_passed": feedback["tests_passed"],
        "tests_total": feedback["tests_total"],
        "verdict": feedback["verdict"],
        "feedback": feedback["feedback"],
        "attempt_number": attempt_number,
        "hint_tier": feedback.get("hint_tier"),
        "hint_ceiling": feedback.get("hint_ceiling"),
        **_student_error_output(test_results, feedback),
    }


# Stdin a student can type into the Run input -- generous for an exercise, but
# keeps a pasted novel from going to Judge0.
MAX_RUN_STDIN_CHARS = 100_000


@app.post("/api/run")
async def api_run(req: RunRequest, student: dict = Depends(_student)):
    """The student page's Run button: runs the code once on the stdin the
    student typed, next to the example test's data files (which they can see
    anyway -- never a graded test's), and returns what it printed. Not graded,
    not stored, no AI feedback: it's for trying things before submitting, so
    the lecturer's dashboard and the attempt count only ever see real submits.
    Shares the submit limiter so a class hammering Run can't starve Judge0."""
    return await anyio.to_thread.run_sync(_run, req, student, limiter=_submit_limiter)


@app.post("/api/lecturer/run")
async def api_lecturer_run(req: RunRequest):
    """The projector's Run on a shown attempt: the same ungraded run as the
    student page's, for the lecturer (no student token, any lecture's task)."""
    return await anyio.to_thread.run_sync(_run, req, None, limiter=_submit_limiter)


def _run(req: RunRequest, student: dict | None):
    """student None: the lecturer's run (api_lecturer_run)."""
    question = get_question(req.question_id)
    if not question:
        raise HTTPException(status_code=404, detail=f"Unknown question_id: {req.question_id!r}")
    if question["status"] != "live":
        raise HTTPException(status_code=409, detail="This question isn't live (not started yet, or already closed).")
    if student is not None:
        _check_student_question(student, question)
    if len(req.stdin) > MAX_RUN_STDIN_CHARS:
        raise HTTPException(status_code=400, detail=f"The input is too long (max {MAX_RUN_STDIN_CHARS:,} characters).")

    rejection_reason = pre_execution_check(
        req.source_code, line_limit=question["line_limit"], extra_packages=question["extra_packages"],
        language=question["language"],
    )
    if rejection_reason:
        return {"rejected": rejection_reason}

    example = question["test_cases"][0] if question["test_cases"] else {}
    output_file = question.get("output_file")
    try:
        r = run_submission(
            req.source_code,
            req.stdin,
            language=question["language"],
            cpu_time_limit=question["cpu_time_limit_s"],
            memory_limit_kb=question["memory_limit_kb"],
            files=test_files.files_of(example) or None,
            output_file=output_file,
        )
    except Judge0Error as e:
        raise HTTPException(status_code=502, detail=str(e))

    return {
        "rejected": None,
        "status": r["status_description"],
        "accepted": r["status_description"] == "Accepted",
        # With a graded output file, `stdout` is that file; what was printed is separate.
        "stdout": r.get("printed_stdout", "") if output_file else (r["stdout"] or ""),
        "stderr": r["stderr"] or "",
        "compile_output": r["compile_output"] or "",
        "message": r["message"] or "",
        "time_s": r["time_s"],
        "exit_code": r["exit_code"],
        "output_file": output_file,
        "output_file_content": r["stdout"] if output_file else None,
    }


def _student_error_output(test_results: list, feedback: dict) -> dict:
    """What a student sees of their program's error output. The full traceback
    only when it comes from the example test (test 1), whose input and files the
    student can see anyway. When only hidden tests crashed, just the error type:
    a traceback from a hidden test could carry that test's input or file
    contents (a program can print them to stderr and crash). Single-test
    questions have no separate example; that test is shown to students, so its
    traceback is too."""
    none = {"traceback": None, "hidden_crash": False, "hidden_error": None}
    if len(test_results) <= 1:
        return {**none, "traceback": feedback.get("traceback")}
    example_traceback = _traceback_for(test_results[:1])
    if example_traceback:
        return {**none, "traceback": example_traceback}
    if feedback.get("traceback"):
        # The classifier reads the error type off the traceback's last line; a
        # multi-line exception message hides it ("Unknown") -- then no type.
        error_type = feedback.get("error_type")
        return {**none, "hidden_crash": True, "hidden_error": error_type if error_type not in (None, "Unknown") else None}
    return none


@app.get("/api/lecturer/submissions")
def api_lecturer_submissions(question_id: str = None):
    # shape_* fields: "same code, different names" grouping for the dashboard's
    # "View code" -- see backend/code_shape.py.
    return [with_shape(row) for row in store.all_submissions(question_id)]


@app.get("/api/lecturer/submissions/{sub_id}")
def api_lecturer_submission_detail(sub_id: int):
    row = store.get_submission(sub_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return with_shape(row)


@app.get("/api/lecturer/questions/{question_id}/progress")
def api_lecturer_question_progress(question_id: str):
    """Live "X/N submitted" counter (see live-submission-progress-scoping-
    decision.md). `expected` is whatever class size the lecturer typed in at
    setup time -- None if they left it blank, in which case `not_submitted`
    is also None rather than a misleading number."""
    question = store.get_question_row(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Not found")
    submitted = store.distinct_student_count(question_id)
    expected = question["expected_students"]
    return {
        "submitted": submitted,
        "expected": expected,
        "not_submitted": (expected - submitted) if expected is not None else None,
    }


@app.get("/api/lecturer/questions/{question_id}/activity")
def api_lecturer_question_activity(question_id: str):
    """Per-student active/idle/away status for the live dashboard's Class
    progress card. Includes everyone who joined the lecture, so a student who
    joined but never opened the editor shows up as "away" instead of not at
    all."""
    question = store.get_question_row(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Not found")
    threshold = question["idle_nudge_seconds"] or DEFAULT_IDLE_SECONDS
    rows = {r["student_name"]: r for r in store.activity_rows(question_id)}
    names = set(rows)
    if question.get("lecture_id") is not None:
        names.update(store.joined_names(question["lecture_id"]))
    result = []
    for name in sorted(names):
        row = rows.get(name)
        if not row:
            result.append({"student_name": name, "status": "away", "idle_seconds": None, "nudged": False})
            continue
        idle_for = _seconds_since(row["last_edit_at"] or row["first_seen_at"])
        if _seconds_since(row["last_seen_at"]) > AWAY_AFTER_SECONDS:
            status = "away"
        elif idle_for >= threshold:
            status = "idle"
        else:
            status = "active"
        result.append(
            {
                "student_name": name,
                "status": status,
                "idle_seconds": int(idle_for),
                "nudged": row["nudge_count"] > 0,
            }
        )
    return result


@app.get("/api/lecturer/clusters")
def api_lecturer_clusters(question_id: str = None):
    return cluster_submissions(question_id)


# "Show on full screen" on the live dashboard -- see aggregation.raise_issue().
# Returns the question's clusters re-ranked, so the dashboard doesn't wait
# for its next poll to show the flagged issue (and its discussion point).
@app.post("/api/lecturer/clusters/raise")
def api_lecturer_clusters_raise(req: RaiseIssueRequest):
    try:
        raise_issue(
            req.question_id, req.exec_verdict, req.error_type, req.submission_ids, req.raised, req.example_submission_id
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return cluster_submissions(req.question_id)


# Serve the built React/TS frontend (setup.html, student.html, lecturer.html
# -- see frontend/README) as static files, mounted last so it never shadows
# the /api/* routes above. Built with `npm run build` from frontend/, which
# outputs to frontend/dist.
_frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_frontend_dir):
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
