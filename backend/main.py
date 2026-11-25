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

import glob
import hashlib
import json
import logging
import os
import time
import uuid
from collections import defaultdict
from datetime import datetime

import anyio
from fastapi import Depends, FastAPI, Header, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.exceptions import RequestValidationError
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
from backend import code_normalize, hint_policy, rate_limit, task_format, task_import, task_runner, test_files
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

# --- Errors ----------------------------------------------------------------------
# What reaches the client is a plain sentence for the person using the page; what
# went wrong inside (exception text, tracebacks, Judge0/LLM/database details, internal
# URLs) only goes to the server log. HTTPException details in this file are written
# for the user; an exception's own text never becomes one, except the exception types
# made for it (task_format.TaskFormatError, store.LectureStateError,
# task_runner.SubmissionFilesError).
log = logging.getLogger("uvicorn.error")

RUNNER_UNAVAILABLE = "The code runner isn't responding right now. Try again in a moment."


def _runner_unavailable(e: Exception) -> HTTPException:
    """Judge0 down or misbehaving -- not the student's code failing, which is a
    normal graded result."""
    log.error("Judge0 request failed: %s", e)
    return HTTPException(status_code=502, detail=RUNNER_UNAVAILABLE)


def _internal_error(what: str) -> HTTPException:
    """For a caught exception that's a bug, not the user's doing. Call from inside
    the except block, so the traceback is logged."""
    error_id = uuid.uuid4().hex[:8]
    log.exception("%s [error %s]", what, error_id)
    return HTTPException(
        status_code=500,
        detail=f"Something went wrong on the server. Try again; if it keeps happening, report error {error_id}.",
    )


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    """Anything no route caught (a database error, a bug): logged in full with an id,
    answered with JSON the pages can show instead of a bare "Internal Server Error"."""
    error_id = uuid.uuid4().hex[:8]
    log.error("Unhandled error on %s %s [error %s]", request.method, request.url.path, error_id,
              exc_info=(type(exc), exc, exc.__traceback__))
    return JSONResponse(
        {"detail": f"Something went wrong on the server. Try again; if it keeps happening, report error {error_id}.",
         "error_id": error_id},
        status_code=500,
    )


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    """A request body/query that doesn't fit the route. FastAPI's default answer is a
    list echoing the input back (a whole submission's code, say), which the pages
    can't show; this names the fields only, and logs the rest."""
    log.info("Invalid request to %s: %s", request.url.path, exc.errors())
    fields = sorted({".".join(str(p) for p in err.get("loc", ()) if p != "body") or "request" for err in exc.errors()})
    return JSONResponse({"detail": f"The request wasn't valid ({', '.join(fields)})."}, status_code=422)


# Reachable without being logged in: logging in, and asking whether you need to.
_LECTURER_PUBLIC_PATHS = {"/api/lecturer/login", "/api/lecturer/logout", "/api/lecturer/session"}


# Routes with a tighter budget on top of the general one (see backend/rate_limit.py).
_STUDENT_RUN_PATHS = {"/api/submit", "/api/run"}
_AI_DRAFT_PATH = "/api/lecturer/hints/draft"


def _is_lecturer_run(path: str) -> bool:
    return path == "/api/lecturer/run" or (path.startswith("/api/lecturer/questions/") and path.endswith("/validate"))


def _client_ip(request: Request) -> str:
    # Behind a proxy this is the real client only with uvicorn's --proxy-headers
    # (README.md); without it every request shares the proxy's address, which the
    # per-address limits are sized to survive anyway.
    return request.client.host if request.client else "unknown"


def _wait_text(seconds: float) -> str:
    seconds = max(1, int(seconds + 0.999))
    if seconds < 90:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    minutes = int(seconds / 60 + 0.999)
    return f"{minutes} minutes"


def _too_many(wait: float, detail: str) -> JSONResponse:
    return JSONResponse(
        {"detail": detail}, status_code=429, headers={"Retry-After": str(max(1, int(wait + 0.999)))}
    )


def _too_many_error(wait: float, detail: str) -> HTTPException:
    return HTTPException(status_code=429, detail=detail, headers={"Retry-After": str(max(1, int(wait + 0.999)))})


def _login_wait(ip: str) -> float:
    """Seconds this address must wait before another lecturer password guess (0: none)."""
    if not rate_limit.enabled():
        return 0.0
    limits = rate_limit.LIMITS
    return max(limits.login_failures_per_ip.retry_after(ip), limits.login_failures_global.retry_after("global"))


def _login_failed(ip: str) -> None:
    rate_limit.LIMITS.login_failures_per_ip.record(ip)
    rate_limit.LIMITS.login_failures_global.record("global")


def _login_wait_detail(wait: float) -> str:
    return f"Too many wrong lecturer passwords. Try again in {_wait_text(wait)}."


# Valid student tokens seen recently -> when to look them up again, so keying the
# limits by token doesn't cost a database read per poll. Only valid tokens go in:
# made-up ones fall back to the per-address limit.
_known_tokens: dict = {}
_KNOWN_TOKEN_SECONDS = 60
_KNOWN_TOKENS_MAX = 20_000


async def _valid_student_token(token: str | None) -> bool:
    if not token:
        return False
    now = time.monotonic()
    if _known_tokens.get(token, 0) > now:
        return True
    if not await anyio.to_thread.run_sync(store.student_for_token, token):
        return False
    if len(_known_tokens) >= _KNOWN_TOKENS_MAX:
        _known_tokens.clear()
    _known_tokens[token] = now + _KNOWN_TOKEN_SECONDS
    return True


@app.middleware("http")
async def guard(request: Request, call_next):
    """Lecturer access and rate limits for every /api/* call, in one place so a new
    route can't forget either.

    Every /api/lecturer/* route is the lecturer's only (see backend/auth.py): it
    exposes students' code, reference solutions and hidden tests, and runs the
    lecture. A wrong X-Lecturer-Token header counts as a wrong password, same as the
    login form, so the header can't be used to guess around the login limit.

    Rate limits (backend/rate_limit.py) are keyed by who's asking -- the lecturer's
    session, else a student's join token, else the client address -- because a whole
    class can share one address. Login and join count their wrong guesses in their
    own routes, since only they know a guess was wrong."""
    path = request.scope["path"]
    if not path.startswith("/api/"):
        return await call_next(request)
    limiting = rate_limit.enabled()
    limits = rate_limit.LIMITS
    ip = _client_ip(request)

    if path.startswith("/api/lecturer/") and path not in _LECTURER_PUBLIC_PATHS:
        header = request.headers.get(auth.HEADER_NAME)
        lecturer = not auth.auth_required() or auth.session_valid(request.cookies.get(auth.COOKIE_NAME))
        if not lecturer and header is not None:
            wait = _login_wait(ip)
            if wait:
                return _too_many(wait, _login_wait_detail(wait))
            lecturer = auth.password_matches(header)
            if not lecturer and limiting:
                _login_failed(ip)
        if not lecturer:
            if limiting and (wait := limits.anonymous_per_ip.take(ip)):
                return _too_many(wait, "Too many requests. Wait a few seconds and try again.")
            return JSONResponse({"detail": "Log in as the lecturer first."}, status_code=401)
        if limiting:
            if wait := limits.lecturer_requests.take("lecturer"):
                return _too_many(wait, "Too many requests. Wait a few seconds and try again.")
            if path == _AI_DRAFT_PATH and (wait := limits.ai_drafts.take("lecturer")):
                return _too_many(wait, f"Hints were drafted several times in a row. Try again in {_wait_text(wait)}.")
            if _is_lecturer_run(path) and (wait := limits.lecturer_runs.take("lecturer")):
                return _too_many(wait, f"Code was run many times in a row. Try again in {_wait_text(wait)}.")
        return await call_next(request)

    if limiting:
        token = request.headers.get("X-Student-Token")
        if await _valid_student_token(token):
            if wait := limits.student_requests.take(token):
                return _too_many(wait, "Too many requests. Wait a few seconds and try again.")
            if path in _STUDENT_RUN_PATHS and (wait := limits.student_runs.take(token)):
                return _too_many(wait, f"You're running code very quickly. Wait {_wait_text(wait)} and try again.")
        elif wait := limits.anonymous_per_ip.take(ip):
            return _too_many(wait, "Too many requests from this network. Wait a few seconds and try again.")
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
    ip = _client_ip(request)
    # Checked before the password, so a locked-out guesser learns nothing.
    if wait := _login_wait(ip):
        raise _too_many_error(wait, _login_wait_detail(wait))
    if not auth.password_matches(req.password):
        if rate_limit.enabled():
            _login_failed(ip)
        await anyio.sleep(1)  # makes guessing slow, without holding a thread
        raise HTTPException(status_code=401, detail="That password isn't right.")
    rate_limit.LIMITS.login_failures_per_ip.reset(ip)
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
    # Test-graded tasks: the editable files, {path: content}. Without it, source_code
    # is taken as the task's (first) editable file, so one-file clients keep working.
    files: dict[str, str] | None = None


class RunRequest(BaseModel):
    # "Run" on the student page: one ungraded run with stdin the student chose.
    question_id: str
    source_code: str
    stdin: str = ""
    # Test-graded tasks: Run runs the visible tests on these files (see _run_tests_mode).
    files: dict[str, str] | None = None


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
    # When hints unlock and what counts as an attempt (backend/hint_policy.py);
    # None = the defaults. Missing keys take the defaults too.
    hint_policy: dict | None = None


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
    hint_policy: dict | None = None


def _checked_hint_policy(raw) -> dict | None:
    """A hint_policy from the setup page, complete with defaults; 400 listing what's wrong."""
    if raw is None:
        return None
    problems = hint_policy.problems_of(raw)
    if problems:
        raise HTTPException(status_code=400, detail=" ".join(problems))
    return hint_policy.from_dict(raw).to_dict()


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
    fields["hint_policy"] = _checked_hint_policy(fields.get("hint_policy"))
    _check_test_files_or_400(fields["test_cases"], fields["output_file"])
    question_id = store.create_question(fields)
    return store.get_question_row(question_id)


@app.post("/api/lecturer/questions/import")
async def api_lecturer_import_question(file: UploadFile):
    """A task folder, zipped (see backend/task_format.py), becomes a draft question. A
    broken folder gets a 400 listing every problem found, one per line.

    Importing a folder again replaces the draft it made before (same task id, as in the
    setup list: not started yet), so fixing a test means edit, zip, import -- not a
    second copy to clean up. The draft keeps its place in the run order and has to be
    checked again. A task that has already run stays as it was; the import then makes
    a new draft. "replaced" in the response says which happened."""
    data = await file.read(task_format.MAX_ZIP_BYTES + 1)
    stem = os.path.splitext(os.path.basename(file.filename or "task"))[0].lower()
    default_id = "-".join(filter(None, "".join(c if c.isalnum() else "-" for c in stem).split("-"))) or "task"
    try:
        spec = task_format.load_task_zip(data, default_id=default_id)
    except task_format.TaskFormatError as e:
        raise HTTPException(status_code=400, detail=str(e))
    fields = task_import.question_fields(spec)
    if spec.grading == "stdout":
        _check_test_files_or_400(fields["test_cases"], fields["output_file"])
    earlier = next((q for q in store.list_question_rows(status="draft", current_lecture_only=True)
                    if (q.get("task_meta") or {}).get("id") == spec.id), None)
    if earlier:
        store.update_question(earlier["id"], {**fields, "validated": 0})
        return {**store.get_question_row(earlier["id"]), "replaced": True}
    question_id = store.create_question(fields)
    return {**store.get_question_row(question_id), "replaced": False}


# The example task folder the setup page offers as a template (its "Download an example"
# link). It doubles as the unit tests' fixture, so it lives under tests/fixtures/; a
# deployment that leaves tests/ out just has no example to offer (404).
EXAMPLE_TASK_DIR = os.path.join(os.path.dirname(__file__), "..", "tests", "fixtures", "pandas-sales-summary")


@app.get("/api/lecturer/example_task")
def api_lecturer_example_task():
    """The example task folder, zipped -- the same format Import reads, to copy and edit."""
    if not os.path.isdir(EXAMPLE_TASK_DIR):
        raise HTTPException(status_code=404, detail="No example task on this server.")
    spec = task_format.load_task_dir(EXAMPLE_TASK_DIR)
    return Response(
        content=task_format.to_zip(spec),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{spec.id}.zip"'},
    )


@app.get("/api/lecturer/questions/{question_id}/export")
def api_lecturer_export_question(question_id: str):
    """The question as a task folder, zipped -- the format the import above reads, so a
    task made in the setup page can be kept in version control or shared."""
    row = store.get_question_row(question_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    spec = task_import.spec_of_question(row)
    return Response(
        content=task_format.to_zip(spec),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{spec.id}.zip"'},
    )


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
    if "hint_policy" in fields:
        fields["hint_policy"] = _checked_hint_policy(fields["hint_policy"])
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
    except rate_limit.RateLimited as e:
        raise _too_many_error(
            e.retry_after, f"The language model has had a lot of requests. Try again in {_wait_text(e.retry_after)}."
        )
    except RuntimeError as e:
        log.warning("hint draft failed: %s", e)
        raise HTTPException(
            status_code=502, detail="Couldn't draft hints right now. Try again in a moment, or write them yourself."
        )
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
    if question["grading_mode"] == "tests":
        return _validate_tests_mode(question)
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
        raise _runner_unavailable(e)

    try:
        starter_problem = _starter_problem(question)
    except Judge0Error as e:
        raise _runner_unavailable(e)

    all_passed = bool(results) and all(r["passed"] for r in results)
    validated = all_passed and not (starter_problem and starter_problem["blocking"])
    store.set_validated(question_id, validated)
    return {"validated": validated, "results": results, "starter_problem": starter_problem}


def _validate_tests_mode(question: dict) -> dict:
    """The validation preview for a test-graded task: the reference solution must pass
    every test (visible and hidden), and the starter must not -- otherwise students
    are "correct" before writing anything. The reference run's tests become the task's
    test list (task_meta["test_ids"]): every later run reports exactly those tests,
    which the clustering's failing-test signature relies on.

    Then each wrong solution in the folder (wrong/<name>/) must fail at least one test,
    and every test task.yaml lists for it -- otherwise the tests don't catch a mistake
    the lecturer expects students to make. Reported per wrong solution in
    "wrong_checks"; any that slips through keeps the task from being ready."""
    reference = task_runner.reference_files(question)
    if not reference:
        raise HTTPException(status_code=400, detail="This task has no reference solution (reference/ in its folder).")
    # Without the stored test list: this run is what defines it.
    unvalidated = {**question, "task_meta": {**question["task_meta"], "test_ids": None}}
    try:
        results = task_runner.run_tests(unvalidated, reference)
        starter_problem = _starter_problem(unvalidated)
    except Judge0Error as e:
        raise _runner_unavailable(e)
    # r.passed, as grading uses: a test the task's author skips counts as passing.
    all_passed = bool(results) and all(r.passed for r in results)
    test_ids = task_runner.expected_test_ids(results)
    if all_passed and not any(t["visibility"] == "visible" for t in test_ids):
        all_passed = False
    try:
        wrong_checks = _check_wrong_solutions(
            {**question, "task_meta": {**question["task_meta"], "test_ids": test_ids}}) if all_passed else []
    except Judge0Error as e:
        raise _runner_unavailable(e)
    validated = (all_passed and not (starter_problem and starter_problem["blocking"])
                 and all(c["ok"] for c in wrong_checks))
    store.update_question(question["id"], {
        "task_meta": {**question["task_meta"], "test_ids": test_ids if all_passed else None},
        "validated": 1 if validated else 0,
    })
    return {"validated": validated, "results": task_runner.as_dicts(results), "starter_problem": starter_problem,
            "wrong_checks": wrong_checks, "grading_mode": "tests"}


def _check_wrong_solutions(question: dict) -> list:
    """One run per wrong/<name>/ -- see _validate_tests_mode."""
    expected = (question.get("task_meta") or {}).get("wrong_solutions") or {}
    checks = []
    for name, files in sorted(task_runner.wrong_solutions(question).items()):
        results = task_runner.run_tests(question, files)
        failing = [r.name for r in results if not r.passed]
        must = list(expected.get(name) or [])
        missed = [t for t in must if t not in failing]
        if not failing:
            message = f"{name} passes every test, so the tests don't catch this mistake."
        elif missed:
            message = f"{name} should fail {', '.join(missed)}, but passes {'it' if len(missed) == 1 else 'them'}."
        else:
            message = f"{name} fails {', '.join(failing)}."
        checks.append({"name": name, "ok": bool(failing) and not missed, "failing": failing,
                       "expected": must, "message": message})
    return checks


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
    to be fine.

    Test-graded tasks: also blocking when the starter files already pass every test
    -- checked even when they're empty (students writing from scratch), since tests
    that pass on nothing are just as broken."""
    starter = question.get("starter_code")
    if not starter or not starter.strip():
        return _starter_passes_everything(question) if question["grading_mode"] == "tests" else None

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

    if question["grading_mode"] == "tests":
        return _starter_passes_everything(question)

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


def _starter_passes_everything(question: dict) -> dict | None:
    """Test-graded tasks: blocking when the editable starter files (as students get
    them, empty ones included) already pass every test."""
    editable = task_runner.editable_files(question)
    starter = task_runner.starter_files(question)
    results = task_runner.run_tests(question, {p: starter.get(p, "") for p in editable})
    if results and all(r.passed for r in results):
        return {"blocking": True, "message": "The starter files already pass every test, so students would be "
                                             "correct without changing anything. Check the tests."}
    return None


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
    except store.LectureStateError as e:
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
    except store.LectureStateError as e:
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
    except store.LectureStateError as e:
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


@app.get("/api/build")
def api_build():
    """The frontend build served now, for pages that don't poll the lecture status (the
    lecturer's pages: frontend/src/shared/UpdateBanner.tsx). See frontend_build()."""
    return {"build": frontend_build()}


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
        return {"finished": finished, "lecture_id": lecture_id, "question": None, "shown_examples": [],
                "shown_position": None, "build": frontend_build()}

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
            "grading_mode": question["grading_mode"],
            # Test-graded tasks: the files of the editor's tabs, name and size only --
            # contents come from api_lecture_workspace (not polled).
            "workspace": _workspace(question, with_content=False) if question["grading_mode"] == "tests" else None,
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
        # The frontend build being served now: a tab whose page carries another one
        # (its <meta name="app-build">) runs old code and reloads -- see frontend_build().
        "build": frontend_build(),
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


def _workspace(question: dict, with_content: bool) -> list:
    """The files a student sees in a test-graded task, in tab order: editable files,
    the other starter files (read-only), visible tests, data files. Never hidden tests
    or the reference. Data files carry content only when asked for one by name
    (api_lecture_workspace_file): they can be megabytes."""
    editable = task_runner.editable_files(question)
    order = {"starter": 1, "test": 2, "data": 3}
    out = []
    for f in sorted((f for f in question.get("task_files") or [] if f["role"] in order),
                    key=lambda f: (order[f["role"]], f["path"] not in editable, f["path"])):
        path = {"test": "tests/", "data": "data/"}.get(f["role"], "") + f["path"]
        entry = {
            "path": path,
            "kind": {"starter": "code", "test": "test", "data": "data"}[f["role"]],
            "editable": f["role"] == "starter" and f["path"] in editable,
            "size": len(f["content"].encode("utf-8")),
        }
        if with_content and f["role"] != "data":
            entry["content"] = f["content"]
        out.append(entry)
    return out


@app.get("/api/lecture/questions/{question_id}/workspace")
def api_lecture_workspace(question_id: str):
    """A test-graded task's editor files with their contents (starter files and visible
    tests; data files by name and size), fetched once when the task opens. Same audience
    as the status poll that announces the task."""
    question = get_question(question_id)
    # Like api_lecture_test_file: only a task that is or was live -- a draft, or one
    # skipped at the end of a lecture, stays private until it actually runs.
    if not question or question["status"] not in ("live", "closed") or question["grading_mode"] != "tests":
        raise HTTPException(status_code=404, detail="Not found")
    return {"files": _workspace(question, with_content=True), "markers": question["task_meta"].get("markers")}


@app.get("/api/lecture/questions/{question_id}/workspace/{path:path}")
def api_lecture_workspace_file(question_id: str, path: str):
    """One file of a test-graded task's workspace with its content (data files open here)."""
    question = get_question(question_id)
    # Like api_lecture_test_file: only a task that is or was live -- a draft, or one
    # skipped at the end of a lecture, stays private until it actually runs.
    if not question or question["status"] not in ("live", "closed") or question["grading_mode"] != "tests":
        raise HTTPException(status_code=404, detail="Not found")
    for f in question.get("task_files") or []:
        shown = {"test": "tests/", "data": "data/"}.get(f["role"], "") + f["path"]
        if f["role"] in ("starter", "test", "data") and shown == path:
            return PlainTextResponse(f["content"])
    raise HTTPException(status_code=404, detail="Not found")


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
            # Rejected before running (empty, too long, ...): shown, but it didn't count.
            "counted": row.get("exec_verdict") != "rejected",
            "not_counted_reason": "rejected" if row.get("exec_verdict") == "rejected" else None,
            "verdict": row["verdict"],
            "tests_passed": row["tests_passed"],
            "tests_total": row["tests_total"],
            "created_at": row["created_at"],
            # The student's own hint, so a reloaded page can show it again.
            "feedback": row["feedback"],
            # Test-graded tasks: the visible tests' results and the hidden count.
            **(_student_test_view(json.loads(row.get("raw_test_results") or "[]"),
                                  (question.get("task_meta") or {}).get("hidden_test_hints"))
               if question["grading_mode"] == "tests" else {}),
        }
        for row in store.all_submissions(question_id)
        if row["student_name"] == name
    ]


@app.get("/api/lecture/hint_state")
def api_lecture_hint_state(question_id: str, student: dict = Depends(_student)):
    """The asking student's attempts and hint unlock state on a question, and the hint
    for their latest counted submission at the level unlocked now. Polled by the
    student page while a hint is pending (timer, lecturer release)."""
    question = store.get_question_row(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Not found")
    _check_student_question(student, question)
    name = student["student_name"]
    state = _hint_state_now(question, name)
    return {
        "state": _hint_state_view(question, state, name),
        "hint": _current_hint(question, store.latest_counted_submission(name, question_id), state.level),
    }


@app.get("/api/lecturer/questions/{question_id}/hint_release")
def api_lecturer_hint_release(question_id: str):
    if not store.get_question_row(question_id):
        raise HTTPException(status_code=404, detail="Not found")
    releases = store.hint_releases(question_id)
    return {"released_level": max((lv for _, lv in releases), default=0)}


@app.post("/api/lecturer/questions/{question_id}/hint_release")
def api_lecturer_release_hint(question_id: str):
    """"Release next hint to everyone": from now on every student on the task has at
    least one more hint, whatever the task's hint policy (backend/hint_policy.py)."""
    question = store.get_question_row(question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Not found")
    if question["status"] != "live":
        raise HTTPException(status_code=409, detail="Hints can only be released while the task is running.")
    return {"released_level": store.release_next_hint(question_id)}


@app.post("/api/lecture/join")
def api_lecture_join(req: LectureJoinRequest, request: Request):
    """Kahoot-style entry gate for the student page (store.check_join_code's
    docstring) -- called once, before the student page starts polling
    /api/lecture/status. The right code gets the student a token (see
    store.join_student()) that every student request after this carries, so
    submitting, running code and the heartbeat need the code too, and nobody
    can act under a classmate's name. Also backs the lobby's live "N joined"
    counter.

    A name already used in this lecture is refused (409), except for the
    browser that holds its token -- a refresh or reopened tab rejoins as the
    same student.

    Rate limits (backend/rate_limit.py), per client address since there's no
    identity yet: wrong codes (a 6-digit code is guessable given enough tries) and
    joins themselves (each one is a new student identity)."""
    limiting = rate_limit.enabled()
    ip = _client_ip(request)
    if limiting and (wait := rate_limit.LIMITS.join_failures_per_ip.retry_after(ip)):
        raise _too_many_error(
            wait, f"Too many wrong codes from this network. Wait {_wait_text(wait)}, then check the code with your lecturer."
        )
    active = store.get_active_lecture()
    if not active:
        raise HTTPException(status_code=404, detail="No lecture is live right now.")
    if not active.get("lobby_opened_at"):
        raise HTTPException(
            status_code=403, detail="This lecture hasn't been opened for joining yet. Check with your lecturer."
        )
    lecture = store.check_join_code(req.code)
    if not lecture:
        if limiting:
            rate_limit.LIMITS.join_failures_per_ip.record(ip)
        raise HTTPException(status_code=403, detail="That code didn't match. Check with your lecturer and try again.")
    student_name = req.student_name.strip()
    if not student_name:
        raise HTTPException(status_code=400, detail="Enter your name.")
    if limiting and (wait := rate_limit.LIMITS.joins_per_ip.take(ip)):
        raise _too_many_error(wait, f"Lots of people just joined from this network. Try again in {_wait_text(wait)}.")
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
    "Try a small step: work the example by hand, or submit just the input-reading part "
    "to see which tests pass. Stuck? Put your hand up."
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


def _hint_state_now(question: dict, student_name: str, attempt_at: float | None = None) -> hint_policy.HintState:
    """The student's hint state on this question (backend/hint_policy.py). attempt_at:
    a counted attempt being graded right now, not stored yet -- its own time is "now"."""
    times = store.counted_attempt_times(student_name, question["id"])
    if attempt_at is not None:
        times.append(attempt_at)
    now = attempt_at if attempt_at is not None else time.time()
    return hint_policy.hint_state(hint_policy.of_question(question), times, store.hint_releases(question["id"]), now)


def _hint_state_view(question: dict, state: hint_policy.HintState, student_name: str) -> dict:
    """What the student page shows about attempts and the next hint."""
    policy = hint_policy.of_question(question)
    left = None if state.unlock_at is None else max(1, int(state.unlock_at - time.time() + 0.999))
    return {
        "level": state.level,
        "counted_attempts": state.counted_attempts,
        "free_attempts_left": state.free_attempts_left,
        "needs_attempt": state.needs_attempt,
        "seconds_until_unlock": left,
        "released_level": state.released_level,
        # Submissions that repeated earlier code (backend/code_normalize.py).
        "duplicates": len(store.duplicates(question["id"], student_name)),
        # Only when the task shows one (informational; changes nothing else).
        "penalty": hint_policy.penalty(
            policy, [r["verdict"] for r in reversed(store.counted_submissions(student_name, question["id"]))]
        ) if policy.penalty else None,
        "policy": {"free_attempts": policy.free_attempts, "unlock": policy.unlock,
                   "interval_seconds": policy.interval_seconds, "penalty": policy.penalty},
    }


def _current_hint(question: dict, row: dict | None, level: int) -> dict | None:
    """The hint for the student's latest counted submission at the level unlocked now
    (a timer or the lecturer may have unlocked more since it was graded). None when
    there's no such submission or it was correct."""
    if not row or row["verdict"] == "correct":
        return None
    results = json.loads(row.get("raw_test_results") or "[]")
    if question["grading_mode"] == "tests":
        feedback = _tests_feedback(question, row["source_code"], results, level)
    else:
        feedback = _stdout_feedback(question, row["source_code"], results, level)
    return {"submission_id": row["id"], "feedback": feedback["feedback"],
            "hint_tier": feedback.get("hint_tier"), "hint_ceiling": feedback.get("hint_ceiling")}


DUPLICATE_NOTICE = "Same code as your attempt #{n}, so it didn't count. Change something before resubmitting."
SIMILAR_NOTICE = ("Almost the same code as your attempt #{n}, so it didn't count towards hints. "
                  "Change something more before resubmitting.")


def _find_duplicate(question: dict, student_name: str, source_code: str, files: dict | None):
    """(kind, earlier submission row, similarity) when this repeats one of the student's
    own counted submissions (backend/code_normalize.py), else None. Compared with all of
    them, not just the last, so alternating two versions doesn't get through. "same":
    identical after normalisation. "similar": at or above the task's
    duplicate_similarity, when that's below 1."""
    policy = hint_policy.of_question(question)
    language = question["language"]
    mine = code_normalize.normalize_submission(source_code, files, language)
    best = None
    my_tokens = code_normalize.submission_tokens(source_code, files, language)
    for row in store.counted_submissions(student_name, question["id"]):
        their_files = json.loads(row["files"]) if row.get("files") else None
        if code_normalize.normalize_submission(row["source_code"], their_files, language) == mine:
            return "same", row, 1.0
        if policy.duplicate_similarity < 1:
            score = code_normalize.similarity(
                my_tokens, code_normalize.submission_tokens(row["source_code"], their_files, language)
            )
            if score >= policy.duplicate_similarity and (best is None or score > best[2]):
                best = ("similar", row, score)
    return best


def _same_code_reply(question: dict, student_name: str, earlier: dict, source_code: str,
                     files: dict | None, now: float) -> dict:
    """A resubmission of identical code: not run, not counted. The student gets the
    earlier attempt's result again, with the hint at the level they're at now."""
    state = _hint_state_now(question, student_name)
    results = json.loads(earlier.get("raw_test_results") or "[]")
    if question["grading_mode"] == "tests":
        feedback = _tests_feedback(question, earlier["source_code"], results, state.level)
        extra = {"traceback": None, "hidden_crash": False, "hidden_error": None,
                 **_student_test_view(results, (question.get("task_meta") or {}).get("hidden_test_hints"))}
    else:
        feedback = _stdout_feedback(question, earlier["source_code"], results, state.level)
        extra = _student_error_output(results, feedback)
    store.save_duplicate({
        "student_name": student_name, "question_id": question["id"], "kind": "same",
        "duplicate_of": earlier["id"], "similarity": 1.0, "source_code": source_code, "files": files,
        "created_at": store.sqlite_ts(now),
    })
    return {
        "submission_id": earlier["id"],
        "tests_passed": earlier["tests_passed"],
        "tests_total": earlier["tests_total"],
        "verdict": earlier["verdict"],
        "feedback": feedback["feedback"],
        "attempt_number": earlier["attempt_number"],
        "hint_tier": feedback.get("hint_tier"),
        "hint_ceiling": feedback.get("hint_ceiling"),
        "counted": False,
        "not_counted_reason": "duplicate",
        "duplicate_of": earlier["attempt_number"],
        "notice": DUPLICATE_NOTICE.format(n=earlier["attempt_number"]),
        "hint_state": _hint_state_view(question, state, student_name),
        **extra,
    }


def _similar_code_reply(question: dict, student_name: str, near: tuple, reply: dict, source_code: str,
                        files: dict | None, now: float) -> dict:
    """A near-duplicate that ran: the student sees its real result, but it isn't stored
    as a submission and doesn't count (reply was graded at the current level)."""
    _, earlier, score = near
    reply = {**reply, "submission_id": None, "attempt_number": None, "counted": False,
             "not_counted_reason": "similar", "duplicate_of": earlier["attempt_number"],
             "notice": SIMILAR_NOTICE.format(n=earlier["attempt_number"])}
    store.save_duplicate({
        "student_name": student_name, "question_id": question["id"], "kind": "similar",
        "duplicate_of": earlier["id"], "similarity": round(score, 4), "source_code": source_code, "files": files,
        "result": reply, "created_at": store.sqlite_ts(now),
    })
    return reply


def _stdout_feedback(question: dict, source_code: str, test_results: list, hint_level: int) -> dict:
    """judge_and_feedback() for a stdout task, plus the two issue types decided here
    (missing output file, hard-coded output). Used when a submission is graded and
    again when its hint is shown at a level unlocked later (timer, lecturer release)."""
    try:
        feedback = judge_and_feedback(
            question["prompt"],
            source_code,
            _graded(test_results),
            language=question["language"],
            hint_level=hint_level,
            hint_ladder=question.get("hint_ladder"),
            example_result=test_results[0] if test_results else None,
            output_file=question.get("output_file"),
        )
    except Exception:
        raise _internal_error("grading feedback failed")

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
        and not reads_input(source_code, question["language"], question.get("starter_code"))
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

    return feedback


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

    # One timestamp for this submission: its hint level is computed for it, and it's
    # stored as created_at, so replaying the attempts later gives the same level.
    now = float(int(time.time()))
    attempt_number = store.next_attempt_number(student_name, req.question_id)
    if question["grading_mode"] == "tests":
        return _submit_tests_mode(req, question, student_name, attempt_number, now)
    tests_total = len(_graded(question["test_cases"]))

    rejection_reason = pre_execution_check(
        req.source_code, line_limit=question["line_limit"], extra_packages=question["extra_packages"],
        language=question["language"],
    )
    if rejection_reason:
        # Rejected before ever reaching Judge0 -- recorded, tagged so it doesn't get
        # mistaken for a graded one, and not counted towards hints.
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
                "created_at": store.sqlite_ts(now),
            }
        )
        return {
            "submission_id": sub_id,
            "tests_passed": 0,
            "tests_total": tests_total,
            "verdict": "error",
            "feedback": f"Your submission wasn't run: {rejection_reason}.",
            "attempt_number": attempt_number,
            "counted": False,
            "not_counted_reason": "rejected",
            "hint_state": _hint_state_view(question, _hint_state_now(question, student_name), student_name),
        }

    duplicate = _find_duplicate(question, student_name, req.source_code, None)
    if duplicate and duplicate[0] == "same":
        return _same_code_reply(question, student_name, duplicate[1], req.source_code, None, now)
    near = duplicate  # "similar" or None: it runs, but a near-duplicate doesn't count

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
        raise _runner_unavailable(e)

    state = _hint_state_now(question, student_name, attempt_at=None if near else now)
    feedback = _stdout_feedback(question, req.source_code, test_results, state.level)
    if near:
        return _similar_code_reply(question, student_name, near, {
            "tests_passed": feedback["tests_passed"], "tests_total": feedback["tests_total"],
            "verdict": feedback["verdict"], "feedback": feedback["feedback"],
            "hint_tier": feedback.get("hint_tier"), "hint_ceiling": feedback.get("hint_ceiling"),
            "hint_state": _hint_state_view(question, state, student_name), **_student_error_output(test_results, feedback),
        }, req.source_code, None, now)

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
            "created_at": store.sqlite_ts(now),
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
        "counted": True,
        "hint_state": _hint_state_view(question, state, student_name),
        **_student_error_output(test_results, feedback),
    }


def _student_test_view(test_results: list, hidden_hints: dict | None = None) -> dict:
    """What a student may see of a test-graded run: every visible test in full (name,
    outcome, message, pytest's short traceback), and of the hidden tests only how many
    there are and how many failed -- no names, no messages: a hidden test's message can
    quote its input or the expected value. The one exception is a sentence the task's
    author wrote for a hidden test (task.yaml's hidden_test_hints), shown when that test
    fails -- still without its name."""
    visible = [r for r in test_results if r.get("visibility") != "hidden"]
    hidden = [r for r in test_results if r.get("visibility") == "hidden"]
    hints = hidden_hints or {}
    hidden_failed_hints = [hints[r.get("test_name")] for r in hidden
                           if not r.get("passed") and r.get("test_name") in hints]
    return {
        "test_results": [
            {"name": r.get("test_name"), "file": r.get("test_file"), "outcome": r.get("outcome"),
             "passed": r.get("passed"), "message": r.get("message") or "", "details": r.get("details") or "",
             # Their own prints, from visible tests only: printed during a hidden test, the
             # output could show that test's data.
             "output": r.get("output") or ""}
            for r in visible
        ],
        "hidden_tests": {"total": len(hidden), "failed": sum(1 for r in hidden if not r.get("passed")),
                         "hints": hidden_failed_hints},
        # Top-level prints: what was printed while the visible tests imported the
        # student's code (never while a hidden test file was imported).
        "load_output": [{"file": r.get("test_file"), "output": r["load_output"]}
                        for r in visible if r.get("load_output")],
    }


def _tests_feedback(question: dict, source_code: str, test_results: list, hint_level: int) -> dict:
    """judge_and_feedback() for a test-graded task -- at submit time and when a hint
    unlocked later is shown for the student's latest submission."""
    try:
        return judge_and_feedback(
            question["prompt"], source_code, test_results, language=question["language"],
            hint_level=hint_level, hint_ladder=question.get("hint_ladder"), grading_mode="tests",
        )
    except Exception:
        raise _internal_error("grading feedback failed")


def _submit_tests_mode(req: SubmitRequest, question: dict, student_name: str, attempt_number: int,
                       now: float) -> dict:
    """/api/submit for a test-graded task: the same steps as a stdout task (pre-execution
    checks, run, classify + hint, store), with pytest results in place of per-test-case
    output. Every test counts toward the verdict, visible ones included."""
    editable = task_runner.editable_files(question)
    tests_total = len((question.get("task_meta") or {}).get("test_ids") or [])
    files = req.files if req.files is not None else task_import.split_files(req.source_code, editable,
                                                                            question["language"])

    def rejected(reason_code: str, message: str) -> dict:
        message = message.rstrip(".")
        sub_id = store.save_submission({
            "student_name": student_name, "question_id": req.question_id, "language": question["language"],
            "source_code": task_import.join_files(files, editable, question["language"]),
            "attempt_number": attempt_number, "tests_passed": 0, "tests_total": tests_total,
            "verdict": "error", "error_type": None, "exec_verdict": "rejected", "rejection_reason": reason_code,
            "feedback": f"Submission rejected before running: {message}.", "discussion_point": None,
            "raw_test_results": json.dumps([]), "files": files, "created_at": store.sqlite_ts(now),
        })
        return {"submission_id": sub_id, "tests_passed": 0, "tests_total": tests_total, "verdict": "error",
                "feedback": f"Your submission wasn't run: {message}.", "attempt_number": attempt_number,
                "counted": False, "not_counted_reason": "rejected",
                "hint_state": _hint_state_view(question, _hint_state_now(question, student_name), student_name)}

    try:
        prepared = task_runner.prepare_submission(question, files)
    except task_runner.SubmissionFilesError as e:
        return rejected("bad_files", str(e))
    source_code = task_import.join_files(prepared, editable, question["language"])
    reason = pre_execution_check(source_code, line_limit=question["line_limit"],
                                 extra_packages=question["extra_packages"], language=question["language"])
    if reason:
        return rejected(reason, reason.replace("_", " "))

    duplicate = _find_duplicate(question, student_name, source_code, prepared)
    if duplicate and duplicate[0] == "same":
        return _same_code_reply(question, student_name, duplicate[1], source_code, prepared, now)
    near = duplicate

    try:
        results = task_runner.run_tests(question, prepared)
    except Judge0Error as e:
        raise _runner_unavailable(e)
    test_results = task_runner.as_dicts(results)

    state = _hint_state_now(question, student_name, attempt_at=None if near else now)
    feedback = _tests_feedback(question, source_code, test_results, state.level)
    if near:
        return _similar_code_reply(question, student_name, near, {
            "tests_passed": feedback["tests_passed"], "tests_total": feedback["tests_total"],
            "verdict": feedback["verdict"], "feedback": feedback["feedback"],
            "hint_tier": feedback.get("hint_tier"), "hint_ceiling": feedback.get("hint_ceiling"),
            "hint_state": _hint_state_view(question, state, student_name), "traceback": None, "hidden_crash": False,
            "hidden_error": None,
            **_student_test_view(test_results, (question.get("task_meta") or {}).get("hidden_test_hints")),
        }, source_code, prepared, now)

    sub_id = store.save_submission({
        "student_name": student_name, "question_id": req.question_id, "language": question["language"],
        "source_code": source_code, "attempt_number": attempt_number,
        "tests_passed": feedback["tests_passed"], "tests_total": feedback["tests_total"],
        "verdict": feedback["verdict"], "error_type": feedback["error_type"],
        "exec_verdict": feedback["exec_verdict"], "rejection_reason": None, "feedback": feedback["feedback"],
        "discussion_point": None, "raw_test_results": json.dumps(test_results), "files": prepared,
        "created_at": store.sqlite_ts(now),
    })
    return {
        "submission_id": sub_id,
        "tests_passed": feedback["tests_passed"],
        "tests_total": feedback["tests_total"],
        "verdict": feedback["verdict"],
        "feedback": feedback["feedback"],
        "attempt_number": attempt_number,
        "hint_tier": feedback.get("hint_tier"),
        "hint_ceiling": feedback.get("hint_ceiling"),
        "counted": True,
        "hint_state": _hint_state_view(question, state, student_name),
        # Visible tests carry their own tracebacks; a hidden crash says nothing more
        # than the hidden count does.
        "traceback": None,
        "hidden_crash": False,
        "hidden_error": None,
        **_student_test_view(test_results, (question.get("task_meta") or {}).get("hidden_test_hints")),
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
    if question["grading_mode"] == "tests":
        return _run_tests_mode(req, question, lecturer=student is None)
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
        raise _runner_unavailable(e)

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


def _run_tests_mode(req: RunRequest, question: dict, lecturer: bool) -> dict:
    """Run for a test-graded task: the visible tests on the student's files, ungraded and
    not stored. The lecturer's run (projector) includes the hidden tests too."""
    editable = task_runner.editable_files(question)
    files = req.files if req.files is not None else task_import.split_files(req.source_code, editable,
                                                                            question["language"])
    try:
        prepared = task_runner.prepare_submission(question, files, splice_markers=not lecturer)
    except task_runner.SubmissionFilesError as e:
        return {"rejected": str(e)}
    reason = pre_execution_check(task_import.join_files(prepared, editable, question["language"]),
                                 line_limit=question["line_limit"], extra_packages=question["extra_packages"],
                                 language=question["language"])
    if reason:
        return {"rejected": reason}
    try:
        results = task_runner.as_dicts(task_runner.run_tests(question, prepared, include_hidden=lecturer))
    except Judge0Error as e:
        raise _runner_unavailable(e)
    view = _student_test_view(results)
    if lecturer:
        view["hidden_test_results"] = [
            {"name": r["test_name"], "file": r["test_file"], "outcome": r["outcome"], "passed": r["passed"],
             "message": r["message"], "details": r["details"], "output": r.get("output") or ""}
            for r in results if r.get("visibility") == "hidden"
        ]
    return {"rejected": None, "grading_mode": "tests", **view}


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
    row = dict(row)
    row["files"] = json.loads(row["files"]) if row.get("files") else None
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
    attempts = _attempt_stats(question)
    rows = {r["student_name"]: r for r in store.activity_rows(question_id)}
    names = set(rows)
    if question.get("lecture_id") is not None:
        names.update(store.joined_names(question["lecture_id"]))
    result = []
    for name in sorted(names):
        row = rows.get(name)
        if not row:
            result.append({"student_name": name, "status": "away", "idle_seconds": None, "nudged": False,
                           **attempts.get(name, _NO_ATTEMPTS)})
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
                **attempts.get(name, _NO_ATTEMPTS),
            }
        )
    return result


_NO_ATTEMPTS = {"counted_attempts": 0, "rejected": 0, "duplicates": 0, "penalty": None, "spam": None}


def _attempt_stats(question: dict) -> dict:
    """Per student on this question: counted attempts, submissions that didn't count
    (rejected before running, duplicates), the penalty when the task shows one, and why
    they look like they're spamming Submit (backend/hint_policy.py), if they do."""
    policy = hint_policy.of_question(question)
    subs = defaultdict(list)
    for row in reversed(store.all_submissions(question["id"])):  # oldest first
        subs[row["student_name"]].append(row)
    dups = defaultdict(list)
    for row in store.duplicates(question["id"]):
        dups[row["student_name"]].append(row)
    stats = {}
    for name in set(subs) | set(dups):
        counted = [r for r in subs[name] if r.get("exec_verdict") != "rejected"]
        times = [store.epoch_of(r["created_at"]) for r in subs[name] + dups[name]]
        stats[name] = {
            "counted_attempts": len(counted),
            "rejected": len(subs[name]) - len(counted),
            "duplicates": len(dups[name]),
            "penalty": hint_policy.penalty(policy, [r["verdict"] for r in counted]) if policy.penalty else None,
            "spam": hint_policy.spam_reason(times, len(dups[name])),
        }
    return stats


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
        log.info("raise_issue refused: %s", e)
        raise HTTPException(status_code=404, detail="That issue isn't on the dashboard any more. Refresh the page.")
    return cluster_submissions(req.question_id)


# Serve the built React/TS frontend (see frontend/README), mounted last so it
# never shadows the /api/* routes above. Built with `npm run build` from
# frontend/, which outputs to frontend/dist.
#
# Each page is served at a clean path (frontend/src/shared/routes.ts -- keep
# the two in step, along with PAGES in frontend/vite.config.ts). The old
# *.html URLs redirect to them, so earlier bookmarks and links still work.
# Anything else gets 404.html with a 404 status (StaticFiles' html mode).
_frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
_PAGES = {
    "/setup": "setup.html",
    "/live": "lecturer.html",
    "/history": "history.html",
    "/present": "present.html",
    "/join": "student.html",
    "/help": "help.html",
    "/privacy": "privacy.html",
}
_LEGACY_PAGES = {f"/{file}": path for path, file in _PAGES.items()} | {"/index.html": "/"}


_build_cache: dict = {"key": None, "build": None}


def frontend_build() -> str | None:
    """A fingerprint of the frontend build being served: a hash of the built pages
    (frontend/dist/*.html, which name every hashed asset). Each page is served with it
    in a <meta name="app-build"> tag, and /api/lecture/status reports the current one,
    so a tab left open across an `npm run build` notices it's running old code
    (frontend/src/shared/build.ts) instead of misreading newer API responses. Rechecked
    when a page file changes; None when there's no build (dev server)."""
    files = sorted(glob.glob(os.path.join(_frontend_dir, "*.html")))
    try:
        key = tuple((f, os.path.getmtime(f)) for f in files)
    except OSError:
        return None
    if key != _build_cache["key"]:
        digest = hashlib.sha256()
        for f in files:
            with open(f, "rb") as fh:
                digest.update(fh.read())
        _build_cache.update(key=key, build=digest.hexdigest()[:12] if files else None)
    return _build_cache["build"]


# Factories, not default arguments: FastAPI would expose a handler's extra
# parameters as query parameters (?file=... choosing what gets served).
def _page_handler(file: str):
    def page() -> HTMLResponse:
        with open(os.path.join(_frontend_dir, file), encoding="utf-8") as f:
            html = f.read()
        build = frontend_build()
        if build:
            html = html.replace("<head>", f'<head>\n    <meta name="app-build" content="{build}">', 1)
        # Never cached: a cached page would carry an old build id and old asset names.
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})

    return page


def _redirect_handler(target: str):
    def redirect(request: Request) -> RedirectResponse:
        query = request.url.query
        return RedirectResponse(f"{target}?{query}" if query else target, status_code=301)

    return redirect


if os.path.isdir(_frontend_dir):
    for _path, _file in _PAGES.items():
        app.add_api_route(_path, _page_handler(_file), methods=["GET", "HEAD"], include_in_schema=False)
    for _old, _new in _LEGACY_PAGES.items():
        app.add_api_route(_old, _redirect_handler(_new), methods=["GET", "HEAD"], include_in_schema=False)
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
