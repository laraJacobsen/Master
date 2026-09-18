"""
Pre-execution validation for student submissions -- checks that run before
code ever reaches Judge0. Catches submissions that aren't really an attempt
(empty box, accidental giant paste, whitespace-only) so they don't burn a
Judge0 slot or an AI feedback call, and so they're stored with a rejection
reason instead of just bouncing an HTTP error at the student.

The line limit and the package allow-list are per-question teacher knobs (see
landing-page-scoping-decision.md) -- callers pass the question's configured
`line_limit`/`extra_packages` through; the defaults here only apply if a
caller doesn't.
"""

import re
import sys

DEFAULT_LINE_LIMIT = 200  # generous for a lecture-hall exercise; catches runaway pastes, not real solutions

REJECTION_REASONS = ["empty", "whitespace_only", "too_long", "encoding_error", "disallowed_package"]

_FROM_IMPORT_RE = re.compile(r"^\s*from\s+([a-zA-Z_][\w.]*)")
_PLAIN_IMPORT_RE = re.compile(r"^\s*import\s+(.+)$")

try:
    _STDLIB_MODULES = set(sys.stdlib_module_names)  # Python 3.10+
except AttributeError:
    # Fallback for Python <3.10, where sys.stdlib_module_names doesn't exist --
    # generous enough to cover typical lecture-hall exercises, not exhaustive.
    _STDLIB_MODULES = {
        "math", "os", "sys", "re", "json", "itertools", "functools", "collections",
        "string", "random", "datetime", "time", "heapq", "bisect", "statistics",
        "typing", "copy", "io", "textwrap", "operator", "decimal", "fractions",
    }


def pre_execution_check(source_code: str, line_limit: int = DEFAULT_LINE_LIMIT, extra_packages=None) -> str | None:
    """Returns a rejection_reason (see REJECTION_REASONS) if the submission
    should be rejected before running, or None if it's fine to send to Judge0."""
    if source_code == "":
        return "empty"

    if source_code.isspace():
        return "whitespace_only"

    try:
        source_code.encode("utf-8")
    except UnicodeEncodeError:
        return "encoding_error"

    if source_code.count("\n") + 1 > line_limit:
        return "too_long"

    if _first_disallowed_import(source_code, extra_packages or []):
        return "disallowed_package"

    return None


def _first_disallowed_import(source_code: str, extra_packages: list) -> str | None:
    allowed = _STDLIB_MODULES | set(extra_packages)
    # Split on ";" too, not just "\n" -- `import os; import numpy` puts a
    # second statement on the same physical line, past where a "^"-anchored
    # per-line match would look.
    statements = (stmt for line in source_code.split("\n") for stmt in line.split(";"))

    for statement in statements:
        from_match = _FROM_IMPORT_RE.match(statement)
        if from_match:
            top_level = from_match.group(1).split(".")[0]
            if top_level not in allowed:
                return top_level
            continue

        plain_match = _PLAIN_IMPORT_RE.match(statement)
        if plain_match:
            # `import os, numpy as np` names several top-level packages in
            # one statement, each optionally aliased.
            for name in plain_match.group(1).split(","):
                top_level = name.strip().split(" as ")[0].strip().split(".")[0]
                if top_level and top_level not in allowed:
                    return top_level

    return None
