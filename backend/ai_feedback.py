"""
AI judging + feedback module.

One combined Claude call per submission: given the question, the student's
code, and the already-computed Judge0 test results, produce a structured
verdict plus student-facing feedback plus a lecturer-facing discussion point.
Structured output is enforced via forced tool use (not by asking Claude to
emit JSON in prose and hoping it parses).

Requires ANTHROPIC_API_KEY in the environment. Model is overridable via
ANTHROPIC_MODEL in case the pinned default is retired later.
"""

import os

from anthropic import Anthropic

_client = None

DEFAULT_MODEL = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250929")

FEEDBACK_TOOL = {
    "name": "submit_feedback",
    "description": "Submit structured feedback on a student's code submission.",
    "input_schema": {
        "type": "object",
        "properties": {
            "verdict": {
                "type": "string",
                "enum": ["correct", "partially_correct", "incorrect", "error"],
                "description": "Overall verdict across all test cases.",
            },
            "error_type": {
                "type": "string",
                "enum": ["none", "syntax", "runtime", "logic", "timeout", "other"],
                "description": "Category of the primary problem, if any.",
            },
            "feedback": {
                "type": "string",
                "description": (
                    "2-4 sentences of feedback FOR THE STUDENT, plain and encouraging. "
                    "Point them toward the issue without just handing them the fixed code."
                ),
            },
            "discussion_point": {
                "type": "string",
                "description": (
                    "One short sentence a lecturer could raise to the whole class about "
                    "this kind of mistake or approach -- generalized beyond this one student."
                ),
            },
        },
        "required": ["verdict", "error_type", "feedback", "discussion_point"],
    },
}


def _get_client():
    global _client
    if _client is None:
        # Anthropic() picks up ANTHROPIC_API_KEY from the environment.
        _client = Anthropic()
    return _client


def _format_cases(test_results: list) -> str:
    lines = []
    for i, r in enumerate(test_results):
        lines.append(
            f"Case {i + 1}: status={r['status_description']}, passed={r['passed']}, "
            f"stdout={r['stdout']!r}, expected={r['expected_stdout']!r}, "
            f"stderr={(r['stderr'] or '')[:300]!r}, "
            f"compile_output={(r['compile_output'] or '')[:300]!r}"
        )
    return "\n".join(lines)


def _guess_error_type(test_results: list) -> str:
    for r in test_results:
        if r["passed"]:
            continue
        status = r["status_description"].lower()
        if "time limit" in status:
            return "timeout"
        if "compilation" in status:
            return "syntax"
        if "runtime error" in status:
            return "runtime"
        return "logic"
    return "none"


def _mock_feedback(test_results: list) -> dict:
    """Canned verdict used when ANTHROPIC_API_KEY isn't set, so the rest of
    the pipeline (Judge0 execution, storage, live lecturer view) can be
    exercised without an API key or cost. Mirrors the shape of a real
    Claude response but with generic text -- not a substitute for it."""
    passed = sum(1 for r in test_results if r["passed"])
    total = len(test_results)

    if total > 0 and passed == total:
        verdict = "correct"
        error_type = "none"
    elif passed == 0:
        verdict = "incorrect"
        error_type = _guess_error_type(test_results)
    else:
        verdict = "partially_correct"
        error_type = _guess_error_type(test_results)

    return {
        "verdict": verdict,
        "error_type": error_type,
        "feedback": (
            f"[Mock feedback -- ANTHROPIC_API_KEY not set] {passed}/{total} test cases passed. "
            "Set ANTHROPIC_API_KEY to get real AI-generated feedback here."
        ),
        "discussion_point": (
            "[Mock] Set ANTHROPIC_API_KEY to get a real lecturer discussion point here."
        ),
        "tests_passed": passed,
        "tests_total": total,
    }


def judge_and_feedback(question_prompt: str, source_code: str, test_results: list, language: str = "python") -> dict:
    """Returns a dict: verdict, error_type, feedback, discussion_point,
    tests_passed, tests_total."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return _mock_feedback(test_results)

    passed = sum(1 for r in test_results if r["passed"])
    total = len(test_results)

    prompt = f"""A student submitted code for this programming exercise:

{question_prompt}

Language: {language}

Student's code:
```
{source_code}
```

Automated test results ({passed}/{total} passed), from running the code against Judge0:
{_format_cases(test_results)}

Call submit_feedback with your assessment."""

    client = _get_client()
    resp = client.messages.create(
        model=DEFAULT_MODEL,
        max_tokens=600,
        tools=[FEEDBACK_TOOL],
        tool_choice={"type": "tool", "name": "submit_feedback"},
        messages=[{"role": "user", "content": prompt}],
    )

    for block in resp.content:
        if block.type == "tool_use" and block.name == "submit_feedback":
            result = dict(block.input)
            result["tests_passed"] = passed
            result["tests_total"] = total
            return result

    raise RuntimeError("Claude response did not include the expected submit_feedback tool call")
