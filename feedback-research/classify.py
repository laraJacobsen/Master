"""
Classification logic, transcribed directly from submission-format-and-error-taxonomy.md
section 3 (the confirmed-against-real-Judge0 taxonomy table). This is the actual logic
that needs to prove itself against real Judge0 output -- not a new design.

Judge0's own status field is nearly useless on its own (a typo, a crash, and OOM all come
back "Runtime Error (NZEC)"), so this reads stdout/stderr/exit_code directly, exactly as
the taxonomy doc describes.
"""

import re

RUNTIME_EXCEPTION_NAMES = [
    "NameError", "TypeError", "IndexError", "AttributeError", "RecursionError",
    "KeyError", "ValueError", "ZeroDivisionError", "ModuleNotFoundError", "ImportError",
    "EOFError",
]


def classify(stdout, stderr, exit_code, expected_output=None, timed_out=False,
             expected_function_name=None):
    """
    Returns (verdict, error_type). error_type is only set when verdict == "runtime_error".
    Mirrors the table in submission-format-and-error-taxonomy.md section 3.

    expected_function_name: the exercise's entry-point function name (e.g. "is_palindrome"),
    used only to distinguish "wrong/missing function name" (verdict function_not_found) from a
    generic NameError elsewhere in the body. Originally hardcoded to "is_palindrome" when this
    only supported one exercise; pass the current exercise's function name to generalize. If
    omitted, this special case never fires and a wrong function name just reports as a plain
    runtime_error/NameError.
    """
    stderr = stderr or ""
    stdout = stdout or ""

    # timeout: no reliable output, cut off by the wall-clock limit
    if timed_out:
        return "timeout", None

    # oom: exit code 137 (SIGKILL) or a bare "Killed" with no Python traceback -- this is
    # the cgroup-enforced kill Judge0/Docker actually uses. A plain `setrlimit`-based cap
    # (what a local subprocess stand-in uses) instead raises a catchable MemoryError with
    # a normal traceback -- still an OOM condition, just a different enforcement mechanism,
    # so it's grouped the same way here.
    if exit_code == 137 or (("Killed" in stderr) and ("Traceback" not in stderr)):
        return "oom", None
    if "MemoryError" in stderr:
        return "oom", None

    # output_limit_exceeded: real Judge0 enforces its own stdout size cap and kills the
    # process outright when a submission floods output, rather than letting it run to the
    # wall-clock timeout. Confirmed against real Judge0 -- this is genuinely distinct from
    # `timeout`, not a subset of it.
    if "File too large" in stderr or "Errno 27" in stderr:
        return "output_limit_exceeded", None

    # syntax_error: python's own parse-time errors -- no separate compile step for Python,
    # so these land in stderr just like runtime exceptions do.
    if "SyntaxError" in stderr:
        return "syntax_error", None
    if "IndentationError" in stderr:
        return "syntax_error", None

    # runtime_error: read the actual last exception line, don't trust a generic status.
    last_line = stderr.strip().splitlines()[-1] if stderr.strip() else ""
    for exc_name in RUNTIME_EXCEPTION_NAMES:
        if last_line.startswith(exc_name) or f" {exc_name}:" in last_line or last_line == exc_name:
            # special case: calling a function that doesn't exist by the expected name
            if exc_name == "NameError" and expected_function_name:
                m = re.search(r"name '([a-zA-Z_]+)' is not defined", last_line)
                if m and m.group(1) == expected_function_name:
                    return "function_not_found", None
            return "runtime_error", exc_name

    if exit_code != 0 and stderr.strip():
        return "runtime_error", "Unknown"

    # nothing crashed: pass vs wrong_answer compares the final printed line, so debug
    # print() clutter left in otherwise-correct code doesn't itself cause a false wrong_answer.
    if expected_output is not None:
        lines = [ln for ln in stdout.splitlines() if ln.strip() != ""]
        last_line = lines[-1].strip() if lines else ""
        if last_line == expected_output.strip():
            return "pass", None
        return "wrong_answer", None

    return "pass", None