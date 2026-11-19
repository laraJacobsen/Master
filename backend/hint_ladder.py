"""
Task-specific wrong-answer hints, drafted by the LLM and approved by the lecturer.

feedback.py's hints are keyed only on the error type, so for a plain wrong answer
the best they can say is "trace your code by hand" -- they never see the task.
This drafts a short ladder for one task instead, from its prompt and reference
solution: a nudge about the approach first, then the concrete construct or
function to use, then -- for the third try and later -- exactly what to change,
just short of the code itself.

The draft is only a draft. The setup page shows it to the lecturer, who edits it
and saves it with the question (questions.hint_ladder). Students only ever see
saved text, never a live model call, so a made-up cause (the reason the LLM was
dropped for per-submission feedback, see ai_feedback.py) gets caught by a human
before any student reads it. Crashes keep feedback.py's error-specific hints.
"""

import json
import re
import uuid

import requests

from backend.aggregation import LLM, _llm_available

LADDER_LENGTH = 3

HINT_LADDER_PROMPT = (
    "You write hints for students solving a short programming exercise in a live class. "
    "A student's program ran but gave the wrong output. Write exactly 3 hints, shown one "
    "per failed attempt, each more specific than the one before. Hints 1 and 2 guide the "
    "student's next step; hint 3 is the last one they get, so it all but gives the answer.\n"
    "  1. ONE key idea for the approach, in plain words, with no code and no function "
    "names. Not a full plan of every step. E.g. \"Go through the list one item at a time "
    "and keep a count as you go.\"\n"
    "  2. Name the one or two tools (construct, function or method) that do the key idea, "
    "and what to use them on. Name them; don't write the finished expression, format "
    "string or line of code. E.g. \"A for loop over the list works here, with a counter "
    "variable you add 1 to.\"\n"
    "  3. Exactly what the finished program does, in order and in words: what to compute, "
    "where, and with which condition or value, including the step students most often get "
    "wrong in THIS exercise. Specific enough to fix the code from directly, but in words, "
    "not a line of code. E.g. \"Start a counter at 0 before the loop, add 1 inside the loop "
    "whenever the item is even, and print the counter once after the loop, not inside it.\"\n"
    "Rules:\n"
    "- Base every hint on the task and the reference solution you're given. The reference "
    "is for you only: never copy code from it.\n"
    "- Talk to the student (\"you\"), in plain text with no markdown. One or two short "
    "sentences for hints 1 and 2, up to three for hint 3.\n"
    "- Be specific to this exercise. Never write generic advice like \"trace your code by "
    "hand\", \"check your logic\", \"compare your output\", \"read the problem again\" or "
    "\"debug step by step\".\n"
    "- Use the names from the exercise's language ({language}).\n"
    "Respond with ONLY a JSON object: {{\"hints\": [\"...\", \"...\", \"...\"]}}. No markdown "
    "fences, no text outside the JSON object."
)

# The vague advice this feature exists to replace -- a draft that falls back to it
# is retried rather than shown to the lecturer as a finished ladder.
_GENERIC_RE = re.compile(
    r"trace (your|the) code|by hand|check your (logic|answer|code)|compare your output"
    r"|read the (problem|task|exercise) again|step by step",
    re.IGNORECASE,
)


def _leaks_reference(hint: str, reference_solution: str) -> bool:
    """True when a hint quotes a whole non-trivial line of the reference solution."""
    squashed = re.sub(r"\s+", "", hint)
    for line in reference_solution.splitlines():
        code = re.sub(r"\s+", "", line)
        if len(code) >= 12 and code in squashed:
            return True
    return False


def _call_llm(prompt: str, language: str, reference_solution: str, starter_code: str | None) -> list:
    parts = [f"Language: {language}", f"Exercise:\n{prompt}"]
    if starter_code and starter_code.strip():
        parts.append(f"Starter code the students begin with:\n{starter_code}")
    parts.append(f"Reference solution (for you only):\n{reference_solution}")
    # IDUN's gateway caches byte-identical requests, so without this a retry or the
    # lecturer's "Draft again" would just get the same draft back.
    parts.append(f"(draft {uuid.uuid4().hex[:8]})")
    headers = {"Authorization": f"Bearer {LLM['api_key']}"} if LLM["api_key"] else {}
    resp = requests.post(
        f"{LLM['base_url']}/chat/completions",
        headers=headers,
        json={
            "model": LLM["model"],
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": HINT_LADDER_PROMPT.format(language=language)},
                {"role": "user", "content": "\n\n".join(parts)},
            ],
        },
        timeout=LLM["timeout"],
    )
    resp.raise_for_status()
    parsed = json.loads(resp.json()["choices"][0]["message"]["content"])
    hints = parsed.get("hints")
    if not (isinstance(hints, list) and len(hints) == LADDER_LENGTH
            and all(isinstance(h, str) and h.strip() for h in hints)):
        raise ValueError(f"expected {LADDER_LENGTH} non-empty hints, got {parsed!r}")
    # Markdown emphasis the model sometimes adds anyway -- the hint is shown as plain text.
    hints = [re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), h).strip() for h in hints]
    for h in hints:
        if _GENERIC_RE.search(h):
            raise ValueError(f"generic hint: {h!r}")
        if _leaks_reference(h, reference_solution):
            raise ValueError(f"hint quotes the reference solution: {h!r}")
    return hints


def draft_hint_ladder(prompt: str, language: str, reference_solution: str,
                      starter_code: str | None = None) -> list:
    """Three hint drafts, attempt 1 first. Raises RuntimeError when no model is
    configured or every try failed -- the caller turns that into an error the
    lecturer sees, since there's no sensible silent fallback for a draft."""
    if not _llm_available():
        raise RuntimeError("No language model is configured (set IDUN_API_KEY or LLM_PROVIDER=ollama).")
    last_error = None
    for _attempt in range(3):
        try:
            return _call_llm(prompt, language, reference_solution, starter_code)
        except Exception as e:
            last_error = e
    raise RuntimeError(f"Couldn't draft hints: {last_error}")


def clean_ladder(hints) -> list | None:
    """What gets stored: blank hints dropped, None when nothing is left."""
    if not hints:
        return None
    kept = [h.strip() for h in hints if isinstance(h, str) and h.strip()]
    return kept or None
