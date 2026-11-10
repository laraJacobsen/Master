"""Data files a test case can attach for the student's program to open by name.

A test case may carry `files`: [{"name": "numbers.txt", "content": "1 2 3\n..."}].
Before that test runs, its files are placed next to the student's program
(judge0_client.run_submission's additional_files), so open("numbers.txt") works in
Python, fopen in C and Files.readAllLines in Java. Tests without files keep working
exactly as before: plain stdin/expected output, read with input().

Different tests can attach different versions of the same file name (a small
numbers.txt for the example, a big one for a graded test); that's how a task gets
bigger or varied test data.

Who may read a file's content (see the student endpoints in main.py):
  - the example test (index 0): always, like its stdin/expected output already are;
  - the graded tests: only once the task's time is up, for the discussion afterwards.
    While students can still submit, graded files stay hidden; otherwise a student
    could print or hard-code the expected answers.

Text files only (the student page shows them in a viewer), at most MAX_FILE_BYTES
each: Judge0 itself caps what a program may print at 1 MB, so test data of the
same order is what a task can meaningfully check.
"""

import re

MAX_FILE_BYTES = 1_000_000
MAX_FILES_PER_TEST = 10
MAX_NAME_LENGTH = 100

# Letters, digits, ".", "-", "_", and "/" between folder names; no leading dot or
# dash per part (hidden files, option-like names), no "..".
_NAME_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*(/[A-Za-z0-9_][A-Za-z0-9_.-]*)*$")

# Files Judge0 writes into the same folder as the program (seen in a live run:
# os.listdir() -> ['numbers.txt', 'run', 'script.py']). A lecturer file with one of
# these names would overwrite the program or its run script.
RESERVED_NAMES = {"script.py", "main.c", "Main.java", "Main.class", "a.out", "run", "compile"}


def files_of(case: dict) -> list:
    """A test case's files; [] for test cases stored before files existed."""
    return case.get("files") or []


def check_test_files(test_cases: list) -> str | None:
    """A message for the lecturer if any test's files can't be used, else None."""
    for number, case in enumerate(test_cases, 1):
        files = files_of(case)
        if len(files) > MAX_FILES_PER_TEST:
            return f"Test {number} has {len(files)} files; a test can have at most {MAX_FILES_PER_TEST}."
        seen = set()
        for f in files:
            name = f["name"]
            if len(name) > MAX_NAME_LENGTH or not _NAME_RE.match(name) or ".." in name.split("/"):
                return (
                    f'Test {number}: "{name}" can\'t be used as a file name. Use letters, digits, '
                    f'".", "-" and "_", with "/" between folder names.'
                )
            if name.split("/")[-1] in RESERVED_NAMES:
                return f'Test {number}: "{name}" is a name the grader uses itself. Pick another name.'
            if name in seen:
                return f'Test {number} has two files called "{name}".'
            seen.add(name)
            if len(f["content"].encode("utf-8")) > MAX_FILE_BYTES:
                return f'Test {number}: "{name}" is larger than 1 MB.'
    return None


def file_meta(files: list) -> list:
    """Name and size only -- what polled endpoints send instead of the content."""
    return [{"name": f["name"], "size": len(f["content"].encode("utf-8"))} for f in files]


def without_contents(test_cases: list) -> list:
    """Test cases with each file reduced to its name and size."""
    return [{**case, "files": file_meta(files_of(case))} for case in test_cases]
