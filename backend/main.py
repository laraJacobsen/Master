"""
FastAPI backend for the interactive-lecture prototype.

Flow per submission:
  1. Student POSTs code to /api/submit
  2. Code runs against the question's test cases on Judge0 (SYNC calls)
  3. ai_feedback.judge_and_feedback() classifies the result (exec_verdict +
     hint text, deterministic) and asks a local Ollama model for a verdict +
     lecturer discussion point
  4. Everything is saved to SQLite
  5. The student gets pass/fail + a tiered hint back immediately
  6. The lecturer page polls /api/lecturer/submissions and sees it appear

Run with:
    OLLAMA_MODEL=llama3.2:3b JUDGE0_BASE_URL=http://localhost:2358 \
        uvicorn backend.main:app --reload --port 8000
from the /root/prototype directory (see README.md).
"""

import json
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend import store
from backend.aggregation import cluster_submissions
from backend.ai_feedback import judge_and_feedback
from backend.judge0_client import Judge0Error, run_test_cases
from backend.questions import get_question, list_questions
from backend.validation import pre_execution_check

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


@app.get("/api/questions")
def api_list_questions():
    return list_questions()


@app.post("/api/submit")
def api_submit(req: SubmitRequest):
    question = get_question(req.question_id)
    if not question:
        raise HTTPException(status_code=404, detail=f"Unknown question_id: {req.question_id!r}")

    attempt_number = store.next_attempt_number(req.student_name, req.question_id)
    tests_total = len(question["test_cases"])

    rejection_reason = pre_execution_check(req.source_code)
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
                "error_type": "other",
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
            req.source_code, question["test_cases"], language=question["language"]
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
            "discussion_point": feedback["discussion_point"],
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


@app.get("/api/lecturer/clusters")
def api_lecturer_clusters(question_id: str = None):
    return cluster_submissions(question_id)


# Serve the plain HTML/JS frontend (student.html, lecturer.html) as static
# files, mounted last so it never shadows the /api/* routes above.
_frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(_frontend_dir):
    app.mount("/", StaticFiles(directory=_frontend_dir, html=True), name="frontend")
