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


def pre_execution_check(source_code: str, line_limit: int = DEFAULT_LINE_LIMIT, extra_packages=None,
                        language: str = "python") -> str | None:
    """Returns a rejection_reason (see REJECTION_REASONS) if the submission
    should be rejected before running, or None if it's fine to send to Judge0.

    The package allow-list is Python's (stdlib + extra_packages) and only applies
    to Python: read as Python, Java's `import java.util.Scanner;` is a disallowed
    package, which rejected every Java submission that read input."""
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

    if language == "python" and _first_disallowed_import(source_code, extra_packages or []):
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


# Names a Python program uses to read standard input. `open` counts too
# (open(0) / open("/dev/stdin")): erring towards "reads input" means an unusual
# but honest solution is never accused of hard-coding.
_INPUT_NAMES = {"input", "stdin", "fileinput", "open"}


def reads_input(source_code: str, language: str = "python", starter_code: str | None = None) -> bool:
    """Whether the program reads its input at all. A program that doesn't can
    only print fixed text, so it can pass a test only by hard-coding that
    test's expected output (see api_submit's ignores_input handling). Python
    only: other languages, and code that doesn't parse, return True so nothing
    is flagged on a guess.

    What the student was handed doesn't count as the student reading -- or
    every program that keeps the starter code would pass:
    - `sys.stdin = open("data.txt")` (the default starter for file tasks) only
      points input() at the task's file; the program still has to read it;
    - helper functions that read (def read_numbers(): ... open(...)) count
      only where they're actually called;
    - top-level statements kept unchanged from the lecturer's `starter_code`
      (`scores = read_scores()`) don't count either, but the names they set
      do: using `scores` afterwards is reading the input.
    A starter statement the student edited is the student's own code again,
    and a starter that doesn't parse (a skeleton to complete) is ignored --
    both err towards "reads input", so an honest solution is never accused."""
    if language != "python":
        return True
    import ast

    try:
        tree = ast.parse(source_code)
    except (SyntaxError, ValueError):
        return True

    # Subtrees that don't count by themselves: stdin redirects, and (found
    # below) the bodies of reading functions and the starter's own statements.
    skipped: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(_is_sys_stdin(t) for t in node.targets):
            skipped.update(id(n) for n in ast.walk(node))
        elif _opens_for_writing(node):
            skipped.add(id(node.func))  # open(name, "w") writes; it reads nothing

    functions = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
    from_starter = _starter_statements(tree, starter_code)

    def uses_reader(node) -> bool:
        return any(id(n) not in skipped and _names_reader(n, readers) for n in ast.walk(node))

    readers = set(_INPUT_NAMES)
    changed = True
    while changed:  # a function that calls a reader is a reader too, and so on
        changed = False
        for fn in functions:
            if fn.name not in readers and uses_reader(fn):
                readers.add(fn.name)
                changed = True
        for stmt in from_starter:
            if uses_reader(stmt):
                bound = {n.id for n in ast.walk(stmt) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Store)}
                if not bound <= readers:
                    readers |= bound
                    changed = True

    for node in [fn for fn in functions if fn.name in readers] + [s for s in from_starter if uses_reader(s)]:
        skipped.update(id(n) for n in ast.walk(node))

    return any(id(n) not in skipped and _names_reader(n, readers) for n in ast.walk(tree))


def _starter_statements(tree, starter_code: str | None) -> list:
    """The program's top-level statements that are still exactly as the
    lecturer's starter code had them (functions aside -- those are handled the
    same whoever wrote them)."""
    import ast

    if not starter_code or not starter_code.strip():
        return []
    try:
        given = {ast.dump(s) for s in ast.parse(starter_code).body}
    except (SyntaxError, ValueError):
        return []
    return [
        s for s in tree.body
        if not isinstance(s, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and ast.dump(s) in given
    ]


def _is_sys_stdin(node) -> bool:
    import ast

    return (
        isinstance(node, ast.Attribute)
        and node.attr == "stdin"
        and isinstance(node.value, ast.Name)
        and node.value.id == "sys"
    )


def _opens_for_writing(node) -> bool:
    """open(name, "w") / "a" / "x" with the mode written out: a file opened
    only to write. Any other open() -- no mode, "r", "r+", "w+", a mode held
    in a variable -- may read, so it still counts as reading."""
    import ast

    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open"):
        return False
    mode = node.args[1] if len(node.args) > 1 else next((k.value for k in node.keywords if k.arg == "mode"), None)
    if not (isinstance(mode, ast.Constant) and isinstance(mode.value, str)):
        return False
    return any(c in mode.value for c in "wax") and "+" not in mode.value and "r" not in mode.value


def _names_reader(node, readers: set) -> bool:
    import ast

    if isinstance(node, ast.Name):
        return node.id in readers
    if isinstance(node, ast.Attribute):
        return node.attr in readers
    return False
