"""
Cheap aggregation over stored submissions: group by (exec_verdict, error_type) -- the
deterministic Judge0-derived taxonomy from backend/hints.py -- and rank clusters by how
many distinct students hit each one. This is the groupby fallback from the
aggregation-pipeline sketch: cheap enough to run live during a lecture, not a semantic
clustering/embedding pipeline.

Discussion points are attached here, one per cluster, generated on first use and cached
in-memory for the rest of the process -- not one per submission. A single student
resubmitting the same broken code repeatedly must not inflate a cluster's count or spawn
a fresh (and possibly differently-worded) discussion point on every attempt: count is
distinct students, and a cluster only gets a discussion point once at least
MIN_STUDENTS_FOR_DISCUSSION distinct students are actually stuck on it -- one student's
idiosyncratic mistake isn't a whole-class talking point.

The one live model call left in this whole project lives here: Ollama optionally writes a
short, warm lead-in sentence, given ONLY the category and how many students hit it (never
any student's code, never raw submissions). It is explicitly not asked to explain or
diagnose the cause -- that's the part that hallucinated even when handed the exact correct
classification directly (see pedagogical-feedback-design-decision.md), so this narrows the
model's job to something it can't get factually wrong: a framing line about a category and
count it was simply told, nothing more.

Crucially, that lead-in is *composed with* hints.mechanism_for_cluster()'s curated factual
sentence, never used in place of it -- an earlier version let Ollama's output replace the
whole discussion point, and it produced pleasant-sounding but content-free lines ("great
practice writing clean code!") that dropped the one thing a lecturer actually needs, which
category this was. The factual sentence is non-negotiable and always present; the model
only ever adds tone in front of it. If Ollama is unreachable or its output fails
validation, hints.discussion_point_for_cluster()'s fully deterministic template (count +
mechanism, no lead-in) is shown instead.
"""

import json
import os
from collections import defaultdict

import requests

from backend import hints, store

MIN_STUDENTS_FOR_DISCUSSION = 2

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.2:3b")

DISCUSSION_SYSTEM_PROMPT = (
    "You are writing the opening line of a talking point a lecturer will read to a "
    "programming class. You will be given only a mistake category and how many students "
    "just hit it -- nothing about any specific student or their code. Immediately after "
    "your sentence, a separate, already-written factual sentence will name and explain "
    "that category -- so do NOT explain, diagnose, guess the technical cause, or restate "
    "what the category means yourself; that sentence is not yours to write. Your only job "
    "is ONE short, warm lead-in that normalizes several students hitting this and sets up "
    "the factual sentence that follows -- e.g. acknowledging it's a common, fixable thing "
    "several people are running into right now.\n"
    "Respond with ONLY a JSON object with exactly this key:\n"
    "  \"discussion_point\": the one-sentence lead-in only -- no technical content\n"
    "No other keys, no markdown fences, no explanation outside the JSON object."
)

_discussion_cache = {}  # (question_id, exec_verdict, error_type) -> str or None


def _ollama_available() -> bool:
    if not OLLAMA_MODEL:
        return False
    try:
        resp = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        resp.raise_for_status()
        available = [m["name"] for m in resp.json().get("models", [])]
    except Exception:
        return False
    return OLLAMA_MODEL in available


def _call_ollama_discussion_point(exec_verdict: str, error_type: str, student_count: int) -> str:
    """One JSON-mode call, given only the category and count -- see module docstring for
    why nothing else is passed in. Raises on network failure, invalid JSON, or a response
    that doesn't satisfy the expected schema -- caller retries/falls back to the
    deterministic template."""
    label = f"{exec_verdict} ({error_type})" if error_type else exec_verdict
    prompt = (
        f"Mistake category: {label}\n"
        f"Distinct students who just hit it: {student_count}\n\n"
        "Respond with the JSON object described in the system prompt."
    )
    resp = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": OLLAMA_MODEL,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": DISCUSSION_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
        },
        timeout=60,
    )
    resp.raise_for_status()
    parsed = json.loads(resp.json()["message"]["content"])
    point = parsed.get("discussion_point")
    if not isinstance(point, str) or not point.strip():
        raise ValueError(f"missing discussion_point in Ollama response: {parsed!r}")
    return point.strip()


def _generate_discussion_point(exec_verdict: str, error_type: str, student_count: int):
    try:
        template = hints.discussion_point_for_cluster(exec_verdict, error_type, student_count)
    except Exception:
        template = None
    if template is None:
        return None  # no recognized family -- nothing safe to say, model or not

    if _ollama_available():
        try:
            mechanism = hints.mechanism_for_cluster(exec_verdict, error_type)
        except Exception:
            mechanism = None
        if mechanism is not None:
            for _attempt in (1, 2):
                try:
                    lead_in = _call_ollama_discussion_point(exec_verdict, error_type, student_count)
                    return f"{lead_in} {mechanism}"
                except Exception:
                    continue

    return template


def _cached_discussion_point(question_id, exec_verdict, error_type, student_count):
    if student_count < MIN_STUDENTS_FOR_DISCUSSION:
        return None
    cache_key = (question_id, exec_verdict, error_type)
    if cache_key not in _discussion_cache:
        _discussion_cache[cache_key] = _generate_discussion_point(
            exec_verdict, error_type, student_count
        )
    return _discussion_cache[cache_key]


def cluster_submissions(question_id: str = None) -> list:
    """Returns clusters ranked by distinct-student count (largest first), each:
      exec_verdict, error_type, count (distinct students), example_submission_id,
      discussion_point (None unless enough distinct students hit this cluster)
    """
    rows = store.all_submissions(question_id)

    clusters = defaultdict(list)
    for row in rows:
        key = (row.get("exec_verdict"), row.get("error_type"))
        clusters[key].append(row)

    result = []
    for (exec_verdict, error_type), members in clusters.items():
        example = members[0]  # all_submissions is already newest-first
        student_count = len({m["student_name"] for m in members})
        result.append(
            {
                "exec_verdict": exec_verdict,
                "error_type": error_type,
                "count": student_count,
                "example_submission_id": example["id"],
                "discussion_point": _cached_discussion_point(
                    example["question_id"], exec_verdict, error_type, student_count
                ),
            }
        )

    result.sort(key=lambda c: c["count"], reverse=True)
    return result
