"""
Classification logic, transcribed directly from submission-format-and-error-taxonomy.md
section 3 (the confirmed-against-real-Judge0 taxonomy table). This is the actual logic
that needs to prove itself against real Judge0 output -- not a new design.

Judge0's own status field is nearly useless on its own (a typo, a crash, and OOM all come
back "Runtime Error (NZEC)"), so this reads stdout/stderr/exit_code directly, exactly as
the taxonomy doc describes.

C and Java (2026-10-20): the checks every language shares (timeout, oom, output limit)
run first, then one crash classifier per language. Python's is the original logic,
unchanged. C's reads the exit code, since a crashed C program prints no exception: the
shell running it reports the signal (128 + signal number). Java's reads the exception
name from the JVM's `Exception in thread "main" ...` line, which is the FIRST line of
the stack trace, where Python's exception is the last. Both were designed against the
CodeNet eval's real Judge0 results -- see feedback-research/codenet-eval/ and
decisions/codenet-classifier-eval-findings-2026-10-19.md.
"""

import re

RUNTIME_EXCEPTION_NAMES = [
    "NameError", "TypeError", "IndexError", "AttributeError", "RecursionError",
    "KeyError", "ValueError", "ZeroDivisionError", "ModuleNotFoundError", "ImportError",
    "EOFError",
]

# 128 + signal number, as reported by the shell Judge0 runs the program from.
# Bus error (SIGBUS) is grouped with segfault: for a student it's the same mistake,
# a memory access that isn't valid.
C_SIGNAL_EXIT_CODES = {
    139: "SegmentationFault",       # SIGSEGV
    135: "SegmentationFault",       # SIGBUS
    136: "FloatingPointException",  # SIGFPE -- integer division or % by zero
    134: "Aborted",                 # SIGABRT -- a failed assert(), or abort()
}
# The same signals as the shell words them in stderr, for results without an exit code.
_C_SIGNAL_MESSAGES = {
    "Segmentation fault": "SegmentationFault",
    "Bus error": "SegmentationFault",
    "Floating point exception": "FloatingPointException",
    "Aborted": "Aborted",
}
OUTPUT_LIMIT_EXIT_CODE = 153  # 128 + SIGXFSZ: wrote past Judge0's output file size cap

_JAVA_EXCEPTION_RE = re.compile(r'Exception in thread "main" ([\w.$]+)')
# The JVM couldn't start the program at all: Judge0 runs `java Main`, so the class must
# be named Main, sit in no package, and have a standard main method.
_JAVA_NO_ENTRY_POINT = (
    "Could not find or load main class",
    "Main method not found",
    "NoClassDefFoundError",
)


def classify(stdout, stderr, exit_code, expected_output=None, timed_out=False,
             expected_function_name=None, language="python"):
    """
    Returns (verdict, error_type). error_type is only set when verdict == "runtime_error".
    Mirrors the table in submission-format-and-error-taxonomy.md section 3.

    expected_function_name: the exercise's entry-point function name (e.g. "is_palindrome"),
    used only to distinguish "wrong/missing function name" (verdict function_not_found) from a
    generic NameError elsewhere in the body. Originally hardcoded to "is_palindrome" when this
    only supported one exercise; pass the current exercise's function name to generalize. If
    omitted, this special case never fires and a wrong function name just reports as a plain
    runtime_error/NameError. Python only.

    language: "python" (default), "c" or "java" -- picks the crash classifier. Error types
    are each language's own names (NameError, SegmentationFault, NoSuchElementException).
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
    # so it's grouped the same way here. (Java's OutOfMemoryError matches "MemoryError" too.)
    if exit_code == 137 or (("Killed" in stderr) and ("Traceback" not in stderr)):
        return "oom", None
    if "MemoryError" in stderr:
        return "oom", None

    # output_limit_exceeded: real Judge0 enforces its own stdout size cap and kills the
    # process outright when a submission floods output, rather than letting it run to the
    # wall-clock timeout. Confirmed against real Judge0 -- this is genuinely distinct from
    # `timeout`, not a subset of it. Python reports it as an OSError (Errno 27); a C
    # program just dies of SIGXFSZ.
    if ("File too large" in stderr or "Errno 27" in stderr
            or "File size limit exceeded" in stderr or exit_code == OUTPUT_LIMIT_EXIT_CODE):
        return "output_limit_exceeded", None

    crash = {"c": _classify_c_crash, "java": _classify_java_crash}.get(language, _classify_python_crash)
    result = crash(stderr, exit_code, expected_function_name)
    if result is not None:
        return result

    # nothing crashed: pass vs wrong_answer compares the final printed line, so debug
    # print() clutter left in otherwise-correct code doesn't itself cause a false wrong_answer.
    if expected_output is not None:
        lines = [ln for ln in stdout.splitlines() if ln.strip() != ""]
        last_line = lines[-1].strip() if lines else ""
        if last_line == expected_output.strip():
            return "pass", None
        return "wrong_answer", None

    return "pass", None


def _classify_python_crash(stderr, exit_code, expected_function_name):
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
    return None


def _classify_c_crash(stderr, exit_code, expected_function_name):
    if exit_code in C_SIGNAL_EXIT_CODES:
        return "runtime_error", C_SIGNAL_EXIT_CODES[exit_code]
    for message, name in _C_SIGNAL_MESSAGES.items():
        if message in stderr:
            return "runtime_error", name

    # A non-zero exit with no signal is main() returning something other than 0 -- in
    # CodeNet mostly `main()` with no `return 0;`, which returns whatever the last call
    # left behind (e.g. printf's character count). Judge0 counts that as a runtime error
    # even when the output is right, so it must not fall through to the output check.
    if exit_code is not None and exit_code != 0:
        return "runtime_error", "NonZeroExit"
    if exit_code is None and stderr.strip():
        return "runtime_error", "Unknown"
    return None


def _classify_java_crash(stderr, exit_code, expected_function_name):
    if any(marker in stderr for marker in _JAVA_NO_ENTRY_POINT):
        return "runtime_error", "MainNotFound"

    m = _JAVA_EXCEPTION_RE.search(stderr)
    if m:
        return "runtime_error", m.group(1).rsplit(".", 1)[-1]  # java.util.X -> X

    if exit_code != 0 and stderr.strip():
        return "runtime_error", "Unknown"
    return None
