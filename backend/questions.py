"""
MVP question bank. One question to start: reads space-separated integers
from stdin, prints their sum. Kept deliberately trivial so the vertical
slice proves the pipeline (submit -> Judge0 -> AI feedback -> lecturer view),
not the question-authoring tooling. Add more entries here to expand later.
"""

QUESTIONS = {
    "sum-ints": {
        "id": "sum-ints",
        "title": "Sum of Integers",
        "prompt": (
            "Read a single line of space-separated integers from standard input "
            "and print their sum on one line."
        ),
        "language": "python",
        "test_cases": [
            {"stdin": "1 2 3\n", "expected_stdout": "6"},
            {"stdin": "10 20 30 40\n", "expected_stdout": "100"},
            {"stdin": "-5 5\n", "expected_stdout": "0"},
            {"stdin": "7\n", "expected_stdout": "7"},
            {"stdin": "1000000 2000000\n", "expected_stdout": "3000000"},
        ],
    }
}


def get_question(question_id: str):
    return QUESTIONS.get(question_id)


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
        for q in QUESTIONS.values()
    ]
