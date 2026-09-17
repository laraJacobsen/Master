"""
Question bank -- backed by SQLite (backend/store.py's `questions` table) rather
than a hardcoded dict, so a lecturer can author a question through the setup/
landing page (see the /api/lecturer/questions* endpoints in main.py) instead of
editing this file directly. store.init_db() seeds the original MVP question
(id "sum-ints") as already `live`/validated, so an existing checkout keeps
working unchanged even before anyone touches the setup page.

`get_question()` returns a question regardless of status (draft/live) -- callers
that care about status (e.g. /api/submit) check `question["status"]` themselves.
`list_questions()` is the student-facing view: only `live` questions, and only
the fields a student should see (no reference_solution, no resource limits).
"""

from backend import store


def get_question(question_id: str):
    return store.get_question_row(question_id)


def list_questions():
    # test_cases[0] is exposed as a worked example so students can confirm the expected
    # input/output format before submitting -- the other test_cases stay server-side
    # only (via get_question), used purely for grading. That split is intentional: see
    # README/frontend/student.html for how the example is shown.
    return [
        {
            "id": q["id"],
            "title": q["title"],
            "prompt": q["prompt"],
            "language": q["language"],
            "example": dict(q["test_cases"][0]) if q["test_cases"] else None,
        }
        for q in store.list_question_rows(status="live")
    ]
