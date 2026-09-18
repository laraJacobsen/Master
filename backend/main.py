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
import os
from datetime import datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import store
from backend.aggregation import (
    carry_forward_discussion_points,
    cluster_submissions,
    session_summary,
    student_recap,
)
from backend.ai_feedback import judge_and_feedback
from backend.judge0_client import Judge0Error, run_test_cases
from backend.questions import get_question, list_questions
from backend.validation import pre_execution_check, DEFAULT_LINE_LIMIT

app = FastAPI(title="Interactive Lecture Prototype")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    store.init_db()


class SubmitRequest(BaseModel):
    student_name: str
    question_id: str
    source_code: str


class TestCase(BaseModel):
    stdin: str
    expected_stdout: str


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


class LectureAdvanceRequest(BaseModel):
    # The dashboard's own question_id, so "Next task"/"Finish lecture" can
    # close it out even if it somehow isn't the most-recently-started live
    # question (see api_lecturer_lecture_next/finish).
    current_question_id: str | None = None


class LectureCreateRequest(BaseModel):
    label: str | None = None


class LectureJoinRequest(BaseModel):
    code: str
    student_name: str


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
    question_id = store.create_question(fields)
    return store.get_question_row(question_id)


@app.get("/api/lecturer/questions/{question_id}")
def api_lecturer_question_detail(question_id: str):
    row = store.get_question_row(question_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return row


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
    if fields:
        # Editing config invalidates any earlier validation preview.
        fields["validated"] = 0
        store.update_question(question_id, fields)
    return store.get_question_row(question_id)


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

    try:
        results = run_test_cases(
            question["reference_solution"],
            question["test_cases"],
            language=question["language"],
            cpu_time_limit=question["cpu_time_limit_s"],
            memory_limit_kb=question["memory_limit_kb"],
        )
    except Judge0Error as e:
        raise HTTPException(status_code=502, detail=str(e))

    all_passed = bool(results) and all(r["passed"] for r in results)
    store.set_validated(question_id, all_passed)
    return {"validated": all_passed, "results": results}


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
    between "Next task" clicks with no drafts left)."""
    lecture = store.get_active_lecture()
    if not lecture:
        return {"lecture": None, "live_question_id": None}
    live_question = store.live_question_row()
    return {"lecture": lecture, "live_question_id": live_question["id"] if live_question else None}


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
    to advance to, so the lecturer knows to use "Finish lecture" instead."""
    if req.current_question_id:
        current = store.get_question_row(req.current_question_id)
        if current and current["status"] == "live":
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
    caller can link straight to its (now generalized) summary view."""
    if req.current_question_id:
        current = store.get_question_row(req.current_question_id)
        if current and current["status"] == "live":
            store.close_question(req.current_question_id)

    lecture = store.get_active_lecture()
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


@app.get("/api/lecture/recap")
def api_lecture_recap(student_name: str):
    """The STATE 2 student recap: this student's own attempted-vs-total and
    per-task verdicts for the lecture that just ended. No class-wide
    comparison -- see student_recap()'s docstring."""
    lecture = store.current_lecture_row()
    if not lecture:
        return {"attempted": 0, "total": 0, "results": []}
    return student_recap(lecture["id"], student_name)


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
    if not question:
        return {"finished": finished, "question": None}

    return {
        "finished": finished,
        "question": {
            "id": question["id"],
            "title": question["title"],
            "prompt": question["prompt"],
            "language": question["language"],
            "example": dict(question["test_cases"][0]) if question["test_cases"] else None,
            "duration_seconds": question["duration_seconds"],
            "started_at": question["started_at"],
            "seconds_remaining": _seconds_remaining(question),
        },
    }


@app.post("/api/lecture/join")
def api_lecture_join(req: LectureJoinRequest):
    """Kahoot-style entry gate for the student page (store.check_join_code's
    docstring) -- called once, before the student page starts polling
    /api/lecture/status. This is a soft UX gate, not real access control:
    /api/submit itself stays open, same as every other endpoint (see the
    "No auth" known simplification in README.md) -- a wrong/missing code
    here just means the student never sees the "enter the lecture" screen
    clear, it doesn't block anything at the API level.

    Also takes the student's name now (not just the code) and records the
    join (store.record_join()) -- what backs the lobby's live "N joined"
    counter. This is the same name the student would otherwise have typed
    again on the answering screen a few minutes later; the student page
    carries it forward instead of asking twice."""
    active = store.get_active_lecture()
    if not active:
        raise HTTPException(status_code=404, detail="No lecture is live right now.")
    if not active.get("lobby_opened_at"):
        raise HTTPException(
            status_code=403, detail="This lecture hasn't been opened for joining yet -- check with your lecturer."
        )
    lecture = store.check_join_code(req.code)
    if not lecture:
        raise HTTPException(status_code=403, detail="That code didn't match. Check with your lecturer and try again.")
    student_name = req.student_name.strip()
    if not student_name:
        raise HTTPException(status_code=400, detail="Enter your name.")
    store.record_join(lecture["id"], student_name)
    return {"lecture_id": lecture["id"], "label": lecture["display_label"]}


@app.post("/api/submit")
def api_submit(req: SubmitRequest):
    question = get_question(req.question_id)
    if not question:
        raise HTTPException(status_code=404, detail=f"Unknown question_id: {req.question_id!r}")
    if question["status"] != "live":
        raise HTTPException(status_code=409, detail="This question isn't live (not started yet, or already closed).")

    attempt_number = store.next_attempt_number(req.student_name, req.question_id)
    tests_total = len(question["test_cases"])

    rejection_reason = pre_execution_check(
        req.source_code, line_limit=question["line_limit"], extra_packages=question["extra_packages"]
    )
    if rejection_reason:
        # Rejected before ever reaching Judge0/Claude -- still recorded as a
        # real attempt, just tagged so it doesn't get mistaken for a graded one.
        sub_id = store.save_submission(
            {
                "student_name": req.student_name,
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
        )
    except Judge0Error as e:
        # Judge0 itself is unreachable/broken -- distinct from the student's
        # code failing, which is a normal 200 response below.
        raise HTTPException(status_code=502, detail=str(e))

    try:
        feedback = judge_and_feedback(
            question["prompt"],
            req.source_code,
            test_results,
            language=question["language"],
            attempt_number=attempt_number,
        )
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"AI feedback failed: {e}")

    sub_id = store.save_submission(
        {
            "student_name": req.student_name,
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
        "traceback": feedback.get("traceback"),
    }


@app.get("/api/lecturer/submissions")
def api_lecturer_submissions(question_id: str = None):
    return store.all_submissions(question_id)


@app.get("/api/lecturer/submissions/{sub_id}")
def api_lecturer_submission_detail(sub_id: int):
    row = store.get_submission(sub_id)
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return row


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


@app.get("/api/lecturer/clusters")
def api_lecturer_clusters(question_id: str = None):
    return cluster_submissions(question_id)


# Serve the built React/TS frontend (setup.html, student.html, lecturer.html
# -- see frontend/README) as static files, mounted last so it never shadows
# the /api/* routes above. Built with `npm run build` from frontend/, which
# outputs to frontend/dist.
_frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(_frontend_dir):
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
