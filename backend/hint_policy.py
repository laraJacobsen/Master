"""
Per-task hint policy: when a student's hints unlock, and what counts as an attempt.

Before this, the hint tier was simply the attempt number, so resubmitting (even the
same code, or an empty file) unlocked the next hint. A policy now says:

  free_attempts         counted attempts that get results but no hint
  unlock                how later hints unlock: "attempt" (every counted attempt),
                        "timer" (interval passed since the last unlock and the student
                        made a counted attempt since), or "both" (a counted attempt made
                        after the interval passed)
  interval_seconds      the timer for "timer" and "both"
  duplicate_similarity  1.0 = only code identical after normalisation is a duplicate
                        (backend/code_normalize.py); lower also refuses to count
                        near-identical code (it still runs)
  penalty               show a penalty counter (informational only)

Stored as one JSON object in questions.hint_policy (NULL = the defaults), written in
task.yaml as a `hint_policy:` block. Kept as one object so later profiles (a
competition mode with hints off, penalty weights) are more keys, not a new schema.
"""

from dataclasses import asdict, dataclass

UNLOCK_MODES = ("attempt", "timer", "both")

# Ranges for task.yaml and the setup page.
MAX_FREE_ATTEMPTS = 20
MAX_INTERVAL_SECONDS = 3600
MIN_DUPLICATE_SIMILARITY = 0.5


@dataclass(frozen=True)
class HintPolicy:
    # One attempt without a hint, so the first thing a student reads is their own
    # result and traceback, not a hint.
    free_attempts: int = 1
    # Each later hint needs a real attempt AND a minute's gap: small edits alone can't
    # farm hints, and a 3-hint ladder still finishes well inside a 10-minute task.
    unlock: str = "both"
    interval_seconds: int = 60
    # Only identical (normalised) code is a duplicate: anything looser starts
    # catching real one-character fixes.
    duplicate_similarity: float = 1.0
    penalty: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


DEFAULT = HintPolicy()
KEYS = tuple(DEFAULT.to_dict())


def problems_of(raw) -> list[str]:
    """What's wrong with a hint_policy mapping (from task.yaml or the API), as
    sentences for the person who wrote it. [] = fine. Missing keys take the defaults."""
    if raw is None:
        return []
    if not isinstance(raw, dict):
        return [f"hint_policy must be a mapping of {', '.join(KEYS)}."]
    problems = []
    unknown = sorted(set(raw) - set(KEYS))
    if unknown:
        problems.append(f"hint_policy: unknown key(s) {', '.join(map(str, unknown))} (known: {', '.join(KEYS)}).")

    def integer(key, low, high):
        value = raw.get(key)
        if key in raw and (isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high):
            problems.append(f"hint_policy: {key} must be a whole number from {low} to {high} (got {value!r}).")

    integer("free_attempts", 0, MAX_FREE_ATTEMPTS)
    integer("interval_seconds", 0, MAX_INTERVAL_SECONDS)
    if "unlock" in raw and raw["unlock"] not in UNLOCK_MODES:
        problems.append(f"hint_policy: unlock must be one of {', '.join(UNLOCK_MODES)} (got {raw['unlock']!r}).")
    similarity = raw.get("duplicate_similarity")
    if "duplicate_similarity" in raw and (
        isinstance(similarity, bool) or not isinstance(similarity, (int, float))
        or not MIN_DUPLICATE_SIMILARITY <= similarity <= 1
    ):
        problems.append(
            f"hint_policy: duplicate_similarity must be a number from {MIN_DUPLICATE_SIMILARITY} to 1 "
            f"(got {similarity!r})."
        )
    if "penalty" in raw and not isinstance(raw["penalty"], bool):
        problems.append(f"hint_policy: penalty must be true or false (got {raw['penalty']!r}).")
    return problems


def from_dict(raw) -> HintPolicy:
    """A stored or validated mapping as a policy; None or {} = the defaults. Raises
    ValueError on a mapping problems_of() would refuse."""
    problems = problems_of(raw)
    if problems:
        raise ValueError("; ".join(problems))
    values = {**DEFAULT.to_dict(), **(raw or {})}
    values["duplicate_similarity"] = float(values["duplicate_similarity"])
    return HintPolicy(**values)


def of_question(question: dict) -> HintPolicy:
    """The policy a question runs under. A question from before policies existed, or
    one stored with something unreadable, gets the defaults."""
    try:
        return from_dict(question.get("hint_policy"))
    except ValueError:
        return DEFAULT
