"""Generates the human/expert spot-check sample for the Headline step's output
(aggregation.py's _headline(): category + discussion point -> "title" + "action"),
per pedagogical-feedback-design-decision.md decision 3. Calls the real IDUN (or
LLM_PROVIDER=ollama) endpoint through the shipped code path, not a mock.

Why this exists: spot-check rounds 1-5 rated only the Label call's discussion
point. The Headline call's title and action are what the lecturer reads first on
the dashboard, and had never been rated.

Inputs: every curated discussion line in feedback-research/feedback.py
(mechanism_for()), with the category label cluster_submissions() would give it.
These are what error clusters, and wrong_answer clusters whose Label call failed
or was gated, send to the Headline call in production.

Headlines for AI-written (Label) notes are NOT here: they're rated in the same
row as their note in Label round 6 (generate_real_discussion_point_sample.py).
A first version of this script fed it round 4's notes, but the Label prompt was
reworded on 2026-11-16, so those notes are no longer what production sends.

No repeat run for variance: tried 2026-11-17 and found the IDUN gateway caches
responses to byte-identical requests (a new note took ~0.7s, the same request
again ~0.1s with identical text), so a second pass only measures the cache. A
variance check needs requests that differ, e.g. a per-run nonce or seed, which
the production call doesn't send.

The CSV also carries a few automatic flags (second person, title length, code-like
tokens in the headline that the note doesn't contain). They are kept out of the
.md on purpose so they can't steer the rating; decision 3 keeps the verdict human.

Output: headline_sample_<date>.csv/.md, never overwriting an existing file.
"""

import csv
import logging
import os
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "feedback-research"))

# Must happen before `backend.aggregation` is imported -- it reads IDUN_API_KEY into
# a module-level constant at import time.
_idun_env = REPO_ROOT / ".idun.env"
if _idun_env.exists():
    for line in _idun_env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

import feedback  # noqa: E402

from backend import aggregation as agg  # noqa: E402

if not agg._llm_available():
    sys.exit("IDUN_API_KEY not set (checked env and .idun.env) -- cannot generate real headlines.")

OUT_DIR = Path(__file__).resolve().parent
DATE_TAG = time.strftime("%Y-%m-%d")
CSV_PATH = OUT_DIR / f"headline_sample_{DATE_TAG}.csv"
MD_PATH = OUT_DIR / f"headline_sample_{DATE_TAG}.md"

# One error_type per runtime family, plus one name that only hits the generic
# fallback family. Aliases (e.g. IndexOutOfBoundsException) are skipped: they
# produce the same text as the family they point to, only with a different name.
_FALLBACK_RUNTIME_EXAMPLE = "ValueError"
# Non-runtime verdicts classify.py emits; error_type is None for all of them.
_OTHER_VERDICTS = [
    "wrong_answer", "syntax_error", "compile_error", "function_not_found",
    "timeout", "oom", "output_limit_exceeded", "rejected",
]

_SECOND_PERSON_RE = re.compile(r"\byou\b|\byour\b|\byou're\b|\byours\b", re.IGNORECASE)
# Code-looking fragments: `backticked`, name(), .method, snake_case, quoted literals,
# operators with an operand. Rough on purpose -- it only flags rows to look at again.
_CODE_TOKEN_RE = re.compile(
    r"`[^`]+`|\b\w+\(\)|\.\w+|\b[a-z]+_\w+\b|(?<!\w)'[^'\s][^']*'(?!\w)|(?<!\w)\"[^\"]+\"(?!\w)|[+\-*/<>]=?\s?\d+|\[[^\]]*\]"
)


def build_inputs():
    inputs = []
    pairs = [("runtime_error", name) for name in feedback._RUNTIME_FAMILIES]
    pairs.append(("runtime_error", _FALLBACK_RUNTIME_EXAMPLE))
    pairs += [(verdict, None) for verdict in _OTHER_VERDICTS]
    for verdict, error_type in pairs:
        note = feedback.mechanism_for(verdict, error_type)
        if note is None:
            raise RuntimeError(f"no curated line for {(verdict, error_type)} -- feedback.py changed?")
        inputs.append({
            "source": f"curated:{verdict}" + (f":{error_type}" if error_type else ""),
            "exercise": "",
            "category": agg._category_label(verdict, error_type),
            "note": note,
        })
    return inputs


def _run_all(inputs):
    """One headline per input, through agg._headline() (2 attempts, falls back to
    None on failure -- the dashboard then shows the note itself)."""
    agg._headline_cache.clear()
    results = []
    for item in inputs:
        t0 = time.monotonic()
        h = agg._headline(item["category"], item["note"])
        results.append((h, time.monotonic() - t0))
    return results


def _flags(note, headline):
    if headline is None:
        return {"second_person": "", "title_words": "", "code_tokens_not_in_note": ""}
    text = f"{headline['title']} {headline['action']}"
    note_lower = note.lower()
    new_tokens = sorted({
        t for t in _CODE_TOKEN_RE.findall(text)
        if t.strip("`'\" ").lower() not in note_lower
    })
    return {
        "second_person": "y" if _SECOND_PERSON_RE.search(text) else "n",
        "title_words": len(headline["title"].split()),
        "code_tokens_not_in_note": " | ".join(new_tokens),
    }


def main():
    for path in (CSV_PATH, MD_PATH):
        if path.exists():
            sys.exit(f"{path} already exists -- it may hold ratings; move it or rename before re-running.")

    logging.basicConfig(level=logging.WARNING)
    inputs = build_inputs()
    print(f"{len(inputs)} inputs, provider={agg.LLM['provider']}, model={agg.LLM['model']}. Run 1...")
    run1 = _run_all(inputs)

    rows = []
    for i, (item, (h1, s1)) in enumerate(zip(inputs, run1), start=1):
        rows.append({
            "id": i,
            "source": item["source"],
            "exercise": item["exercise"],
            "category": item["category"],
            "note": item["note"],
            "title": h1["title"] if h1 else "",
            "action": h1["action"] if h1 else "",
            "failed": "n" if h1 else "y",
            "seconds": f"{s1:.2f}",  # ~0.1s means the gateway served a cached response
            **_flags(item["note"], h1),
            "is_faithful_to_note_y_n": "",
            "title_names_mistake_y_n": "",
            "is_lecturer_facing_y_n": "",
            "is_actionable_y_n": "",
            "rater_note": "",
        })

    with CSV_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    failed = sum(r["failed"] == "y" for r in rows)
    md = [
        f"# Headline sample -- human/expert spot-check (round 1)",
        "",
        f"Generated {DATE_TAG} against the live endpoint (provider `{agg.LLM['provider']}`, model "
        f"`{agg.LLM['model']}`). {len(rows)} rows, one per curated (hand-written) "
        "discussion line in feedback.py. Headlines for AI-written notes are rated in Label round 6. {failed} call(s) failed and fell back to showing the note as "
        "the headline (marked below; nothing to rate).",
        "",
        "The model saw only the category and the note -- never code. For each row:",
        "",
        "- **is_faithful_to_note**: do the title and action say only what the note says? (No new "
        "cause, code detail, example or claim.)",
        "- **title_names_mistake**: does the title name the actual mistake, not just repeat the "
        "category?",
        "- **is_lecturer_facing**: addressed to the lecturer, never the students?",
        "- **is_actionable**: is the action something a lecturer could do in class right now?",
        "",
        "Rate in the companion CSV. Leave its automatic-flag columns until after rating.",
        "",
        "**Pass rule (write this before rating, don't change it after):**",
        "",
        "> ",
        "",
    ]
    for r in rows:
        heading = f"## Row {r['id']} -- {r['category']}"
        if r["exercise"]:
            heading += f" ({r['exercise']})"
        md += [heading, "", "**Note the model was given:**", f"> {r['note']}", ""]
        if r["failed"] == "y":
            md += ["**Headline call failed** -- the dashboard shows the note itself.", ""]
            continue
        md += [
            f"**Title:** {r['title']}",
            "",
            f"**Action:** {r['action']}",
            "",
            "- is_faithful_to_note_y_n:",
            "- title_names_mistake_y_n:",
            "- is_lecturer_facing_y_n:",
            "- is_actionable_y_n:",
            "",
        ]
    MD_PATH.write_text("\n".join(md))

    flagged = sum(bool(r["code_tokens_not_in_note"]) or r["second_person"] == "y" for r in rows)
    print(f"Done. {len(rows)} rows, {failed} failed, {flagged} auto-flagged.")
    print(f"  {CSV_PATH}")
    print(f"  {MD_PATH}")


if __name__ == "__main__":
    main()
