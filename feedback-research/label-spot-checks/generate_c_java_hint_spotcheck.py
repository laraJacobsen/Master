"""Generates the human/expert spot-check sample for the C and Java hint families added
2026-10-20 (feedback-research/feedback.py; see decisions/codenet-classifier-eval-
findings-2026-10-19.md). Same idea as the Label rounds in this folder, but for the
student-facing hints, which are curated text rather than generated: nothing here calls
a model. What can still be wrong is the fit -- a hint can be true of its error type in
general and still point a particular student at the wrong thing (e.g. the segfault hint
names scanf's missing &, but that student indexed past the end of an array).

Each row is a REAL CodeNet submission (feedback-research/codenet-eval/'s sample, already
run through Judge0 into results.jsonl) that production classifies into one of the new
families, with what the student page would show for it: the error output box, and the
hint on attempts 1-3 (SHIPPED_TIER_CAP; tier 4 is never shown). Plus the lecturer's
discussion point for a group of such students. Up to PER_TYPE rows per (language,
verdict, error_type), drawn with a fixed seed, spread over different problems first.

Rate per row:
  hint_fits_y_n         would tiers 2-3 point THIS student toward their actual mistake?
  wording_ok_y_n        correct for the language, clear to a novice, no wrong claim
                        (e.g. "crashed before producing output" when it printed things)?
  discussion_ok_y_n     is the discussion point true of this submission, and useful to
                        a lecturer?
  rater_note            what's wrong, or what the hint should say instead

Pre-read (Claude Code, 2026-10-20, before any human rating): the first generation was
read through for outright misfits, and four hint texts were revised before this sample
was regenerated for rating -- so the human round rates the revised texts:
  - the generic runtime fallback (rows with IllegalStateException/FileNotFoundException)
    said "crashed before producing output" and pointed at "the line at the bottom of the
    traceback" -- Python wording; a Java stack trace has the failing line at the top.
    Now language-neutral (this also changes Python's fallback text).
  - SegmentationFault named only array indexes and scanf's missing &; two of three rows
    crashed on printf('#') (a char where a string goes) and on a 2^31-element array.
  - NullPointerException / NumberFormatException: three rows were readLine() returning
    null after the input ran out, which the hints didn't mention.

Output: c_java_hint_spotcheck_<DATE_TAG>.csv/.md next to this script. Re-running
overwrites them, so copy a rated CSV aside (or bump DATE_TAG) before regenerating.

Needs CodeNet extracted locally (CODENET_DIR, see codenet-eval/select_problems.py) for
the source code; results.jsonl for the Judge0 output.

Usage:
    python feedback-research/label-spot-checks/generate_c_java_hint_spotcheck.py
"""

import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "feedback-research" / "codenet-eval"))

from backend import hints  # noqa: E402
from backend.ai_feedback import _traceback_for  # noqa: E402
from run_judge0 import JUDGE0_LANGUAGE, RESULTS_PATH  # noqa: E402
from sample_submissions import source_path  # noqa: E402

DATE_TAG = "2026-10-20"
CSV_PATH = HERE / f"c_java_hint_spotcheck_{DATE_TAG}.csv"
MD_PATH = HERE / f"c_java_hint_spotcheck_{DATE_TAG}.md"
SEED = 20261020
PER_TYPE = 3
ERROR_OUTPUT_MAX_LINES = 12
LANGUAGES = ("C", "Java")
FENCE = {"C": "c", "Java": "java"}

RATING_COLUMNS = ["hint_fits_y_n", "wording_ok_y_n", "discussion_ok_y_n", "rater_note"]


def main():
    by_family = defaultdict(list)
    with open(RESULTS_PATH, encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("skipped") or r["language"] not in LANGUAGES:
                continue
            verdict, error_type = hints.classify_submission(
                [r["result"]], language=JUDGE0_LANGUAGE[r["language"]])
            # The new families: compile_error, and every C/Java runtime error type.
            if verdict == "compile_error" or verdict == "runtime_error":
                by_family[(r["language"], verdict, error_type)].append(r)

    rng = random.Random(SEED)
    rows = []
    for (lang, verdict, error_type), records in sorted(by_family.items(), key=lambda kv: (kv[0][0], -len(kv[1]))):
        records = sorted(records, key=lambda r: r["submission_id"])
        rng.shuffle(records)
        # One per problem first, so a family's rows aren't all the same exercise.
        picked, seen_problems = [], set()
        for r in records + records:
            if len(picked) == PER_TYPE:
                break
            if r in picked or (r["problem_id"] in seen_problems and len(seen_problems) < len({x["problem_id"] for x in records})):
                continue
            picked.append(r)
            seen_problems.add(r["problem_id"])

        for r in picked:
            code = source_path({**r, "filename_ext": "c" if lang == "C" else "java"}).read_text(
                encoding="utf-8", errors="replace")
            error_output = _traceback_for([r["result"]]) or ""
            tiers = [hints.hint_for_verdict(verdict, error_type, attempt)["hint_text"] for attempt in (1, 2, 3)]
            rows.append({
                "id": len(rows) + 1,
                "language": lang,
                "family": f"{verdict}/{error_type}" if error_type else verdict,
                "family_size_in_eval": len(records),
                "submission_id": r["submission_id"],
                "problem_id": r["problem_id"],
                "codenet_status": r["codenet_status"],
                "code": code,
                "error_output_shown_to_student": error_output,
                "hint_attempt_1": tiers[0],
                "hint_attempt_2": tiers[1],
                "hint_attempt_3": tiers[2],
                "discussion_point": hints.discussion_point_for_cluster(verdict, error_type, 2),
                **{c: "" for c in RATING_COLUMNS},
            })

    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)

    md = [
        f"# C/Java hint spot-check ({DATE_TAG})",
        "",
        "Generated by `generate_c_java_hint_spotcheck.py` (see its docstring). Real CodeNet "
        "submissions, each shown with what the student page would show it: the error output "
        "box and the hint on attempts 1-3, plus the lecturer's discussion point. The hints "
        "are curated text, not generated; the question is whether they fit *this* "
        "student's actual mistake.",
        "",
        "Rate in the CSV (same rows): **hint_fits** (would attempts 2-3 point this student "
        "toward their actual mistake?), **wording_ok** (correct for the language, clear to a "
        "novice, no false claim), **discussion_ok** (true of this submission, useful to a "
        "lecturer), plus a note.",
        "",
    ]
    for row in rows:
        error_lines = row["error_output_shown_to_student"].rstrip().splitlines()
        if len(error_lines) > ERROR_OUTPUT_MAX_LINES:
            error_lines = error_lines[:ERROR_OUTPUT_MAX_LINES] + ["... (truncated here; the student sees all of it)"]
        md += [
            f"## Row {row['id']} -- {row['language']} `{row['family']}` "
            f"({row['problem_id']}, {row['family_size_in_eval']} in the eval)",
            "",
            f"```{FENCE[row['language']]}",
            row["code"].rstrip(),
            "```",
            "",
            "**Error output the student sees:**",
            "",
            "```",
            *(error_lines or ["(none)"]),
            "```",
            "",
            f"1. {row['hint_attempt_1']}",
            f"2. {row['hint_attempt_2']}",
            f"3. {row['hint_attempt_3']}",
            "",
            f"**Discussion point (lecturer):** {row['discussion_point']}",
            "",
            "- hint_fits_y_n: ______",
            "- wording_ok_y_n: ______",
            "- discussion_ok_y_n: ______",
            "- rater_note: ______",
            "",
        ]
    MD_PATH.write_text("\n".join(md), encoding="utf-8")

    families = sorted({r["family"] for r in rows})
    print(f"Wrote {len(rows)} rows across {len(families)} families to {CSV_PATH.name} / {MD_PATH.name}")
    for fam in families:
        print(f"  {fam}: {sum(r['family'] == fam for r in rows)}")


if __name__ == "__main__":
    main()
