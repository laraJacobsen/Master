"""
Thin wrapper around a self-hosted Judge0 instance's synchronous submission API.

Reuses the exact request pattern already validated during the earlier latency
and scaling benchmarks (judge0_latency_bench.py / judge0_scaling_bench.py):
POST /submissions?base64_encoded=true&wait=true with base64-encoded
source_code/stdin, then read back status.description, stdout, stderr,
compile_output, and timing.

Per-question CPU time / memory limits (see landing-page-scoping-decision.md)
are teacher-facing knobs, but capped server-side at MAX_CPU_TIME_LIMIT /
MAX_MEMORY_LIMIT_KB so a question's config can't starve the shared Judge0
instance -- those ceilings are an operator-level setting (env var), not
something a question's setup page exposes.
"""

import base64
import os

import requests

JUDGE0_BASE_URL = os.environ.get("JUDGE0_BASE_URL", "http://localhost:2358")

DEFAULT_CPU_TIME_LIMIT = 5  # seconds
DEFAULT_MEMORY_LIMIT_KB = 128000  # ~125MB

MAX_CPU_TIME_LIMIT = float(os.environ.get("MAX_CPU_TIME_LIMIT", "15"))
MAX_MEMORY_LIMIT_KB = int(os.environ.get("MAX_MEMORY_LIMIT_KB", "256000"))

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


def run_submission(
    source_code: str,
    stdin: str,
    language: str = "python",
    timeout: int = 15,
    cpu_time_limit: float = None,
    memory_limit_kb: int = None,
) -> dict:
    """Submit one piece of code + stdin to Judge0 synchronously.

    cpu_time_limit (seconds) and memory_limit_kb are clamped to
    MAX_CPU_TIME_LIMIT/MAX_MEMORY_LIMIT_KB regardless of what's passed in.

    Returns a normalized result dict:
      status_id, status_description, stdout, stderr, compile_output, message,
      time_s, memory_kb
    """
    if language not in LANGUAGE_IDS:
        raise ValueError(f"Unsupported language: {language!r}. Supported: {list(LANGUAGE_IDS)}")

    # "x if x is not None else DEFAULT", not "x or DEFAULT" -- an explicit 0
    # is a real (if unusual) limit, not "unset", and `or` would silently
    # replace it with the default since 0 is falsy.
    cpu_time_limit = cpu_time_limit if cpu_time_limit is not None else DEFAULT_CPU_TIME_LIMIT
    memory_limit_kb = memory_limit_kb if memory_limit_kb is not None else DEFAULT_MEMORY_LIMIT_KB
    cpu_time_limit = min(cpu_time_limit, MAX_CPU_TIME_LIMIT)
    memory_limit_kb = min(memory_limit_kb, MAX_MEMORY_LIMIT_KB)
    # The HTTP call itself must outlast Judge0's own cpu_time_limit (wait=true
    # blocks until Judge0 finishes), plus headroom for compilation/queueing.
    timeout = max(timeout, cpu_time_limit + 10)

    payload = {
        "language_id": LANGUAGE_IDS[language],
        "source_code": _b64(source_code),
        "stdin": _b64(stdin),
        "cpu_time_limit": cpu_time_limit,
        "memory_limit": memory_limit_kb,
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
        "exit_code": data.get("exit_code"),
    }


def run_test_cases(
    source_code: str,
    test_cases: list,
    language: str = "python",
    cpu_time_limit: float = None,
    memory_limit_kb: int = None,
) -> list:
    """Run one submission's code against a list of test cases.

    Each test case is {"stdin": "...", "expected_stdout": "..."}.
    Returns a list of per-case result dicts (the run_submission dict, plus
    case_index / stdin / expected_stdout / passed). A single failing test case
    does not stop the rest from running -- only a genuine Judge0 connectivity
    failure raises (Judge0Error), which callers should let propagate as a
    502-style error rather than silently grading it wrong.
    """
    results = []
    for i, case in enumerate(test_cases):
        result = run_submission(
            source_code,
            case["stdin"],
            language=language,
            cpu_time_limit=cpu_time_limit,
            memory_limit_kb=memory_limit_kb,
        )
        actual = (result["stdout"] or "").strip()
        expected = case["expected_stdout"].strip()
        result["case_index"] = i
        result["stdin"] = case["stdin"]
        result["expected_stdout"] = case["expected_stdout"]
        result["passed"] = (result["status_description"] == "Accepted" and actual == expected)
        results.append(result)
    return results
