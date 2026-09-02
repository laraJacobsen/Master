"""
Thin wrapper around a self-hosted Judge0 instance's synchronous submission API.

Reuses the exact request pattern already validated during the earlier latency
and scaling benchmarks (judge0_latency_bench.py / judge0_scaling_bench.py):
POST /submissions?base64_encoded=true&wait=true with base64-encoded
source_code/stdin, then read back status.description, stdout, stderr,
compile_output, and timing.
"""

import base64
import os

import requests

JUDGE0_BASE_URL = os.environ.get("JUDGE0_BASE_URL", "http://localhost:2358")

LANGUAGE_IDS = {
    "python": 71,
    "c": 50,
    "java": 62,
}


def _b64(s: str) -> str:
    return base64.b64encode(s.encode("utf-8")).decode("ascii")


def _un_b64(s):
    if s is None:
        return None
    return base64.b64decode(s).decode("utf-8", errors="replace")


class Judge0Error(RuntimeError):
    """Raised when Judge0 itself can't be reached or returns something unexpected.

    NOT raised when a student's code fails to compile/run/produce the right
    answer -- that is a normal graded outcome, reflected in status_description.
    """


def run_submission(source_code: str, stdin: str, language: str = "python", timeout: int = 15) -> dict:
    """Submit one piece of code + stdin to Judge0 synchronously.

    Returns a normalized result dict:
      status_id, status_description, stdout, stderr, compile_output, message,
      time_s, memory_kb
    """
    if language not in LANGUAGE_IDS:
        raise ValueError(f"Unsupported language: {language!r}. Supported: {list(LANGUAGE_IDS)}")

    payload = {
        "language_id": LANGUAGE_IDS[language],
        "source_code": _b64(source_code),
        "stdin": _b64(stdin),
    }

    try:
        resp = requests.post(
            f"{JUDGE0_BASE_URL}/submissions",
            params={"base64_encoded": "true", "wait": "true"},
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
    except requests.RequestException as e:
        raise Judge0Error(f"Could not reach Judge0 at {JUDGE0_BASE_URL}: {e}") from e

    data = resp.json()
    status = data.get("status") or {}

    return {
        "status_id": status.get("id"),
        "status_description": status.get("description"),
        "stdout": _un_b64(data.get("stdout")),
        "stderr": _un_b64(data.get("stderr")),
        "compile_output": _un_b64(data.get("compile_output")),
        "message": _un_b64(data.get("message")),
        "time_s": data.get("time"),
        "memory_kb": data.get("memory"),
    }


def run_test_cases(source_code: str, test_cases: list, language: str = "python") -> list:
    """Run one submission's code against a list of test cases.

    Each test case is {"stdin": "...", "expected_stdout": "..."}.
    Returns a list of per-case result dicts (the run_submission dict, plus
    case_index / expected_stdout / passed). A single failing test case does
    not stop the rest from running -- only a genuine Judge0 connectivity
    failure raises (Judge0Error), which callers should let propagate as a
    502-style error rather than silently grading it wrong.
    """
    results = []
    for i, case in enumerate(test_cases):
        result = run_submission(source_code, case["stdin"], language=language)
        actual = (result["stdout"] or "").strip()
        expected = case["expected_stdout"].strip()
        result["case_index"] = i
        result["expected_stdout"] = case["expected_stdout"]
        result["passed"] = (result["status_description"] == "Accepted" and actual == expected)
        results.append(result)
    return results
