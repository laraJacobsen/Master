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


# --- unlocking ------------------------------------------------------------------------


@dataclass(frozen=True)
class HintState:
    """Where one student stands on one task, at `now`."""

    # Hints unlocked so far (0 = none). Not capped: the hint shown is
    # min(level, the ceiling of whatever the student got wrong).
    level: int
    # Submissions that ran and weren't duplicates.
    counted_attempts: int
    # Counted attempts still to go before the first hint (0 once hints have started).
    free_attempts_left: int
    # The next unlock needs a new counted attempt (after unlock_at, if that's set).
    needs_attempt: bool
    # When the timer part of the next unlock is satisfied (epoch seconds), else None.
    unlock_at: float | None
    # The lecturer's released level (0 = none), already included in `level`.
    released_level: int


def hint_state(policy: HintPolicy, attempt_times: list[float], releases: list[tuple[float, int]],
               now: float) -> HintState:
    """Replays a student's counted attempts (epoch seconds) and the lecturer's releases
    ((time, level), "everyone has at least this hint from now on") in time order.

    - An attempt is eligible once the student has used their free attempts. The first
      eligible attempt unlocks hint 1 (whatever the mode), unless a release got there
      first.
    - After that, per policy.unlock:
        attempt  every eligible attempt unlocks the next hint;
        timer    the next hint unlocks at max(last unlock + interval, the first eligible
                 attempt after the last unlock) -- so it can unlock between submissions,
                 but never without a try since the last one;
        both     an eligible attempt made at least `interval` after the last unlock.
    - A release lifts the level to the released one (if lower) and counts as an unlock,
      so the timer runs from it. It works regardless of free attempts.
    """
    interval = policy.interval_seconds
    events = sorted([(t, 1, None) for t in attempt_times] + [(t, 0, lv) for t, lv in releases])
    level = 0
    last_unlock = None  # time of the last unlock
    tried_since = None  # time of the first eligible attempt after the last unlock
    counted = 0
    released = 0

    def unlock(at):
        nonlocal level, last_unlock, tried_since
        level += 1
        last_unlock = at
        tried_since = None

    def run_timer(until):
        # "timer" unlocks that came due before `until`, one interval at a time.
        while policy.unlock == "timer" and level >= 1 and tried_since is not None:
            due = max(last_unlock + interval, tried_since)
            if due > until:
                return
            unlock(due)

    for t, is_attempt, release_level in events:
        run_timer(t)
        if not is_attempt:
            released = max(released, release_level)
            if level < release_level:
                level = release_level - 1
                unlock(t)
            continue
        counted += 1
        if counted <= policy.free_attempts:
            continue
        if level == 0:
            unlock(t)
        elif policy.unlock == "attempt":
            unlock(t)
        elif policy.unlock == "both":
            if t >= last_unlock + interval:
                unlock(t)
        elif tried_since is None:  # timer
            tried_since = t
            run_timer(t)
    run_timer(now)

    free_left = 0 if level >= 1 else max(policy.free_attempts + 1 - counted, 1)
    if level == 0:
        needs_attempt, unlock_at = True, None
    elif policy.unlock == "attempt":
        needs_attempt, unlock_at = True, None
    elif policy.unlock == "both":
        due = last_unlock + interval
        needs_attempt, unlock_at = True, (due if due > now else None)
    elif tried_since is None:  # timer, nothing tried since the last unlock
        needs_attempt, unlock_at = True, last_unlock + interval
    else:  # timer, tried: unlocks on its own at the due time
        needs_attempt, unlock_at = False, max(last_unlock + interval, tried_since)
    if unlock_at is not None and unlock_at <= now:
        unlock_at = None
    return HintState(level=level, counted_attempts=counted, free_attempts_left=free_left,
                     needs_attempt=needs_attempt, unlock_at=unlock_at, released_level=released)


# --- penalty and spam -------------------------------------------------------------------


def penalty(policy: HintPolicy, counted_verdicts: list[str]) -> int:
    """Counted wrong attempts after the free ones, up to the first correct one
    (verdicts oldest first). Informational only: nothing else reads it."""
    total = 0
    for number, verdict in enumerate(counted_verdicts, 1):
        if verdict == "correct":
            break
        if number > policy.free_attempts:
            total += 1
    return total


# "Likely spamming" on the lecturer's dashboard. Shared settings, not per task: they
# describe behaviour, not the task's pedagogy.
SPAM_DUPLICATES = 3  # this many submissions that repeated earlier code
SPAM_BURST_COUNT = 5  # or this many submits (any kind) ...
SPAM_BURST_SECONDS = 60  # ... within this many seconds


def spam_reason(submit_times: list[float], duplicate_count: int) -> str | None:
    """Why a student looks like they're spamming Submit, or None. submit_times: every
    submit, counted or not, any order."""
    if duplicate_count >= SPAM_DUPLICATES:
        return f"{duplicate_count} resubmissions of the same code"
    times = sorted(submit_times)
    for i in range(len(times) - SPAM_BURST_COUNT + 1):
        if times[i + SPAM_BURST_COUNT - 1] - times[i] <= SPAM_BURST_SECONDS:
            return f"{SPAM_BURST_COUNT} submits within {SPAM_BURST_SECONDS} s"
    return None
