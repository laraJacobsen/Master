"""
Deterministic verdict classification from raw Judge0 results.

Independent of Claude's own verdict/error_type judgment in ai_feedback.py --
that one is coarse and phrased for student feedback. This one is a fixed
taxonomy meant for lecture-wide aggregation (grouping submissions by what
went wrong): pass, wrong_answer, syntax_error, runtime_error, timeout, oom,
function_not_found, rejected. "rejected" is assigned by validation.py before
Judge0 ever runs; classify() only ever returns the other seven.
"""

TAXONOMY = [
    "pass",
    "wrong_answer",
    "syntax_error",
    "runtime_error",
    "timeout",
    "oom",
    "function_not_found",
    "rejected",
]


def classify(test_results: list) -> str:
    if test_results and all(r["passed"] for r in test_results):
        return "pass"

    for r in test_results:
        if r["passed"]:
            continue

        status = (r["status_description"] or "").lower()
        stderr = (r["stderr"] or "").lower()

        if "time limit" in status:
            return "timeout"
        # Judge0 doesn't compile Python -- a SyntaxError surfaces as a
        # "Runtime Error (NZEC)" status with the traceback in stderr, not a
        # "Compilation Error" status (confirmed against a live Judge0 instance).
        if "compilation" in status or "syntaxerror" in stderr:
            return "syntax_error"
        # An OOM-killed process shows no distinct Judge0 status and no
        # MemoryError -- just the OS OOM killer's "Killed" in stderr
        # (confirmed against a live Judge0 instance).
        if "memory limit" in status or "memoryerror" in stderr or "killed" in stderr:
            return "oom"
        if "runtime error" in status:
            if "nameerror" in stderr and "is not defined" in stderr:
                return "function_not_found"
            return "runtime_error"
        return "wrong_answer"

    return "wrong_answer"
