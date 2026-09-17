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


@app.get("/api/questions")
def api_list_questions():
    return list_questions()


@app.get("/api/lecturer/questions")
def api_lecturer_list_questions():
    return store.list_question_rows()


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

    fields = {k: v for k, v in req.model_dump().items() if v is not None}
    if "test_cases" in fields:
        fields["test_cases"] = [tc if isinstance(tc, dict) else tc.model_dump() for tc in req.test_cases]
    if fields:
        # Editing config invalidates any earlier validation preview.
        fields["validated"] = 0
        store.update_question(question_id, fields)
    return store.get_question_row(question_id)


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
    store.start_question(question_id)
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

    store.start_question(next_question["id"])
    return {"started": store.get_question_row(next_question["id"])}


@app.post("/api/lecturer/lecture/finish")
def api_lecturer_lecture_finish(req: LectureAdvanceRequest):
    """Closes the dashboard's current question (if it's still live) and
    marks the whole lecture finished -- the "Finish lecture" button. Distinct
    from just running out of draft questions: the lecturer can end early
    even with drafts left unstarted."""
    if req.current_question_id:
        current = store.get_question_row(req.current_question_id)
        if current and current["status"] == "live":
            store.close_question(req.current_question_id)

    store.set_lecture_finished(True)
    return {"finished": True}


@app.get("/api/lecturer/lecture/summary")
def api_lecturer_lecture_summary(lecture_seq: int | None = None):
    """The STATE 2 post-lecture view: per-task submission rate + verdict
    trend across every task in the lecture, plus carry-forward discussion
    points (issues that recurred across 2+ tasks). Defaults to the lecture
    that just ended -- see store.current_lecture_seq()'s docstring for why
    that stays correct right after "End session" without the caller having
    to pass anything."""
    seq = lecture_seq if lecture_seq is not None else store.current_lecture_seq()
    return {
        "lecture_seq": seq,
        "tasks": session_summary(seq),
        "carry_forward_discussion_points": carry_forward_discussion_points(seq),
    }


@app.get("/api/lecture/recap")
def api_lecture_recap(student_name: str):
    """The STATE 2 student recap: this student's own attempted-vs-total and
    per-task verdicts for the lecture that just ended. No class-wide
    comparison -- see student_recap()'s docstring."""
    seq = store.current_lecture_seq()
    return student_recap(seq, student_name)


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
    finished = store.get_lecture_finished()
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
