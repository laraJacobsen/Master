"""
Pre-execution validation for student submissions -- checks that run before
code ever reaches Judge0. Catches submissions that aren't really an attempt
(empty box, accidental giant paste, whitespace-only) so they don't burn a
Judge0 slot or an AI feedback call, and so they're stored with a rejection
reason instead of just bouncing an HTTP error at the student.
"""

MAX_LINES = 500  # generous for a lecture-hall exercise; catches runaway pastes, not real solutions

REJECTION_REASONS = ["empty", "whitespace_only", "too_long", "encoding_error"]


def pre_execution_check(source_code: str) -> str | None:
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

    if source_code.count("\n") + 1 > MAX_LINES:
        return "too_long"

    return None
