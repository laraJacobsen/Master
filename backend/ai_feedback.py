"""
AI judging + feedback module.

verdict + discussion_point come from a local Ollama model (JSON-mode chat call).
The actual hint text shown to the student comes from the tiered taxonomy in
feedback-research/ (via backend/hints.py), not from the model -- see
feedback-research/pedagogical-feedback-design-decision.md. Ollama is not asked to
produce feedback text at all.

exec_verdict (the deterministic Judge0-result classification, also used for
lecturer aggregation) is computed here too via hints.classify_submission(), so
main.py doesn't need its own separate classifier call -- one classification of
test_results feeds both the hint text and the stored exec_verdict.

Falls back to a deterministic mock (heuristic verdict from test pass/fail counts)
whenever Ollama is unreachable, OLLAMA_MODEL isn't pulled, or two consecutive
JSON-mode calls fail to produce schema-conforming output -- this must never 500
the submission endpoint.
"""

import json
import os

import requests

from backend.hints import classify_submission, hint_for_verdict

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")

VERDICTS = ("correct", "partially_correct", "incorrect", "error")
ERROR_TYPES = ("none", "syntax", "runtime", "logic", "timeout", "other")

JUDGE_SYSTEM_PROMPT = (
    "You are grading a student's code submission for a programming exercise. "
    "Respond with ONLY a JSON object with exactly these keys:\n"
    f"  \"verdict\": one of {list(VERDICTS)}\n"
    f"  \"error_type\": one of {list(ERROR_TYPES)}\n"
    "  \"discussion_point\": one short sentence a lecturer could raise to the "
    "whole class about this kind of mistake or approach, generalized beyond this "
    "one student.\n"
    "No other keys, no markdown fences, no explanation outside the JSON object."
)


def _ollama_available() -> bool:
    if not OLLAMA_MODEL:
        return False
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        available = [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        return False
    return OLLAMA_MODEL in available


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


_TRACEBACK_MAX_CHARS = 2000


def _traceback_for(test_results: list) -> str:
    """Raw stderr from the first failing test case, or None if it passed or
    produced no stderr (e.g. a plain wrong-answer). Several hint tiers (see
    feedback-research/feedback.py) explicitly tell the student to "read the
    traceback" -- that only makes sense if the student can actually see one."""
    failing = next((r for r in test_results if not r["passed"]), None)
    if failing is None or not failing.get("stderr"):
        return None
    stderr = failing["stderr"]
    if len(stderr) > _TRACEBACK_MAX_CHARS:
        stderr = stderr[:_TRACEBACK_MAX_CHARS] + "\n... (truncated)"
    return stderr


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
    """Canned verdict used when Ollama isn't reachable/configured, so the rest of
    the pipeline (Judge0 execution, storage, live lecturer view) can be
    exercised without a local model running. Mirrors the shape of a real
    Ollama response but with generic text -- not a substitute for it."""
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
            f"[Mock feedback -- Ollama not reachable] {passed}/{total} test cases passed. "
            f"Start Ollama and set OLLAMA_MODEL (currently {OLLAMA_MODEL!r}) to get real "
            "AI-generated verdict/discussion point here."
        ),
        "discussion_point": (
            "[Mock] Start Ollama to get a real lecturer discussion point here."
        ),
        "tests_passed": passed,
        "tests_total": total,
    }


def _call_ollama(prompt: str) -> dict:
    """One JSON-mode call. Raises on network failure, invalid JSON, or a response
    that doesn't satisfy the expected schema -- caller retries/falls back."""
    resp = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        },
        timeout=60,
    )
    resp.raise_for_status()
    parsed = json.loads(resp.json()["message"]["content"])
    if parsed.get("verdict") not in VERDICTS:
        raise ValueError(f"bad verdict in Ollama response: {parsed!r}")
    if parsed.get("error_type") not in ERROR_TYPES:
        raise ValueError(f"bad error_type in Ollama response: {parsed!r}")
    if not isinstance(parsed.get("discussion_point"), str) or not parsed["discussion_point"].strip():
        raise ValueError(f"missing discussion_point in Ollama response: {parsed!r}")
    return {
        "verdict": parsed["verdict"],
        "error_type": parsed["error_type"],
        "discussion_point": parsed["discussion_point"],
    }


def judge_and_feedback(
    question_prompt: str,
    source_code: str,
    test_results: list,
    language: str = "python",
    attempt_number: int = 1,
    expected_function_name: str = None,
) -> dict:
    """Returns a dict: verdict, error_type, feedback, discussion_point,
    tests_passed, tests_total, hint_tier, hint_ceiling, exec_verdict, traceback."""
    passed = sum(1 for r in test_results if r["passed"])
    total = len(test_results)
    baseline_feedback = (
        f"All {total} test cases passed!"
        if total and passed == total
        else f"{passed}/{total} test cases passed. Review the cases that didn't match."
    )

    if not _ollama_available():
        result = _mock_feedback(test_results)
    else:
        prompt = f"""A student submitted code for this programming exercise:

{question_prompt}

Language: {language}

Student's code:
```
{source_code}
```

Automated test results ({passed}/{total} passed), from running the code against Judge0:
{_format_cases(test_results)}

Respond with the JSON object described in the system prompt."""

        judged = None
        for _attempt in (1, 2):
            try:
                judged = _call_ollama(prompt)
                break
            except Exception:
                continue

        result = (
            {**judged, "feedback": baseline_feedback, "tests_passed": passed, "tests_total": total}
            if judged is not None
            else _mock_feedback(test_results)
        )

    try:
        exec_verdict, taxonomy_error_type = classify_submission(test_results, expected_function_name)
        hint = hint_for_verdict(exec_verdict, taxonomy_error_type, attempt_number)
    except Exception:
        exec_verdict = "pass" if passed == total and total > 0 else "wrong_answer"
        hint = {"hint_text": None, "hint_tier": None, "hint_ceiling": None}

    if hint["hint_text"] is not None:
        result["feedback"] = hint["hint_text"]
    result["hint_tier"] = hint["hint_tier"]
    result["hint_ceiling"] = hint["hint_ceiling"]
    result["exec_verdict"] = exec_verdict
    result["traceback"] = _traceback_for(test_results)
    return result
