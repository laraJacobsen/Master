"""
AI judging + feedback module.

verdict and error_type are computed deterministically from test pass/fail counts
and hints.classify_submission() (the same Judge0-result classifier that also
produces exec_verdict and the student-facing hint text) -- not guessed by the
model. Ollama's only job is discussion_point: a lecturer talking-point sentence
written *about* that already-determined classification, not an independent
re-diagnosis of it. Asking a local 3B model to classify the error itself from
raw stdout/stderr produced discussion points that contradicted the real cause
(e.g. blaming an undefined variable on a submission that actually just had a
typo or a missing print) -- grounding the prompt in the deterministic verdict
fixes that.

The actual hint text shown to the student comes from the tiered taxonomy in
feedback-research/ (via backend/hints.py) -- see
feedback-research/pedagogical-feedback-design-decision.md.

exec_verdict (the deterministic Judge0-result classification, also used for
lecturer aggregation) is computed here too via hints.classify_submission(), so
main.py doesn't need its own separate classifier call -- one classification of
test_results feeds both the hint text and the stored exec_verdict.

Falls back to a deterministic mock discussion point whenever Ollama is
unreachable, OLLAMA_MODEL isn't pulled, or two consecutive JSON-mode calls fail
to produce schema-conforming output -- this must never 500 the submission
endpoint.
"""

import json
import os

import requests

from backend.hints import classify_submission, hint_for_verdict

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")

# Coarse buckets for the `verdict`/`error_type` columns the frontend badges and
# lecturer cluster view render -- derived deterministically, see _coarse_verdict()
# and _guess_error_type() below.
VERDICTS = ("correct", "partially_correct", "incorrect", "error")
ERROR_TYPES = ("none", "syntax", "runtime", "logic", "timeout", "other")

JUDGE_SYSTEM_PROMPT = (
    "You are helping a lecturer prepare a whole-class talking point about a student's "
    "programming submission. Automated analysis has already determined exactly what went "
    "wrong -- you will be told that classification below. Treat it as ground truth; do not "
    "second-guess, re-diagnose, or contradict it.\n"
    "Respond with ONLY a JSON object with exactly this key:\n"
    "  \"discussion_point\": one short sentence a lecturer could raise to the whole class "
    "about this kind of mistake, generalized beyond this one student.\n"
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


def _coarse_verdict(exec_verdict: str, passed: int, total: int) -> str:
    """Deterministic verdict bucket for the frontend badges (correct/partially_correct/
    incorrect/error), derived from the same exec_verdict classify_submission() already
    computed -- no LLM guessing needed for this part."""
    if total > 0 and passed == total:
        return "correct"
    if passed > 0:
        return "partially_correct"
    return "incorrect" if exec_verdict in ("wrong_answer", "pass") else "error"


def _mock_discussion_point(exec_verdict: str, error_type: str = None) -> str:
    """Canned discussion point used when Ollama isn't reachable/configured, so the rest
    of the pipeline (Judge0 execution, storage, live lecturer view) can be exercised
    without a local model running."""
    label = f"{exec_verdict} ({error_type})" if error_type else exec_verdict
    return (
        f"[Mock -- Ollama not reachable] Automated classification: {label}. Start Ollama "
        f"and set OLLAMA_MODEL (currently {OLLAMA_MODEL!r}) to get a real lecturer "
        "discussion point here."
    )


def _call_ollama(prompt: str) -> str:
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
    point = parsed.get("discussion_point")
    if not isinstance(point, str) or not point.strip():
        raise ValueError(f"missing discussion_point in Ollama response: {parsed!r}")
    return point


def judge_and_feedback(
    question_prompt: str,
    source_code: str,
    test_results: list,
    language: str = "python",
    attempt_number: int = 1,
    expected_function_name: str = None,
) -> dict:
    """Returns a dict: verdict, error_type, feedback, discussion_point,
    tests_passed, tests_total, hint_tier, hint_ceiling, exec_verdict."""
    passed = sum(1 for r in test_results if r["passed"])
    total = len(test_results)
    baseline_feedback = (
        f"All {total} test cases passed!"
        if total and passed == total
        else f"{passed}/{total} test cases passed. Review the cases that didn't match."
    )

    try:
        exec_verdict, taxonomy_error_type = classify_submission(test_results, expected_function_name)
        hint = hint_for_verdict(exec_verdict, taxonomy_error_type, attempt_number)
    except Exception:
        exec_verdict = "pass" if passed == total and total > 0 else "wrong_answer"
        taxonomy_error_type = None
        hint = {"hint_text": None, "hint_tier": None, "hint_ceiling": None}

    verdict = _coarse_verdict(exec_verdict, passed, total)
    error_type = _guess_error_type(test_results)

    discussion_point = None
    if verdict != "correct":
        discussion_point = _mock_discussion_point(exec_verdict, taxonomy_error_type)
        if _ollama_available():
            classification = (
                f"{exec_verdict} ({taxonomy_error_type})" if taxonomy_error_type else exec_verdict
            )
            prompt = f"""A student submitted code for this programming exercise:

{question_prompt}

Language: {language}

Student's code:
```
{source_code}
```

Automated test results ({passed}/{total} passed), from running the code against Judge0:
{_format_cases(test_results)}

Automated analysis already classified this submission as: {classification}.

Respond with the JSON object described in the system prompt."""

            for _attempt in (1, 2):
                try:
                    discussion_point = _call_ollama(prompt)
                    break
                except Exception:
                    continue

    result = {
        "verdict": verdict,
        "error_type": error_type,
        "feedback": baseline_feedback,
        "discussion_point": discussion_point,
        "tests_passed": passed,
        "tests_total": total,
    }

    if hint["hint_text"] is not None:
        result["feedback"] = hint["hint_text"]
    result["hint_tier"] = hint["hint_tier"]
    result["hint_ceiling"] = hint["hint_ceiling"]
    result["exec_verdict"] = exec_verdict
    return result
