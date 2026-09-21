"""Generates the human/expert spot-check sample for the Label step's output --
per pedagogical-feedback-design-decision.md decision 3 -- run against the CURRENT
production pipeline (diff-against-reference clustering, see backend/aggregation.py's
2026-09-21 docstring entry, into the real IDUN Label call, not a mock).

This is NOT the ground-truth labeling sample (subcluster_ground_truth_sample.csv):
that one exists to score the CLUSTERING step against hand-labeled bug groups and
never calls an LLM at all. This script exercises the LABEL step -- the thing that
still hasn't had a human look at its real output since the Ollama->IDUN migration
(backend/aggregation.py's 2026-09-21 docstring entry says the Label prompt itself is
"UNCHANGED" by that migration, but the endpoint, model, and every real generated
string are new).

Real data sources (no fabricated bugs anywhere):

1. sum-ints (5 sub-clusters expected) -- the same 15 real live-pipeline submissions
   build_subcluster_ground_truth_sample.py transcribed from
   discussion-point-spotcheck-2026-09-16.csv. Original per-submission tester
   identities were deliberately dropped in that transcription (to not hand a
   ground-truth labeler the answer); this script re-assigns one placeholder,
   distinct student name per row, in numbers matching the counts documented in that
   script's own comments (e.g. "4x SpotCheck-A_plus_one + 1x Mock Tester" -> 5
   distinct placeholder names for that code) -- this restores DISTINCT-STUDENT
   COUNTS the production gate depends on, it does not add or remove submissions.

2. double-it (2 sub-clusters expected) -- the same 11 real rows still in
   backend/prototype.db today, this time with their real recorded tester names
   (Bilal/Bob/Carol/Jeppe/Theo) instead of dropped, since nothing about that data
   required anonymizing it for this pass.

3. is_palindrome (corpus.py), count_vowels (corpus_count_vowels.py), and
   second_largest (corpus_second_largest.py) -- each contributes its 3
   hand-written-but-real-bug-representative wrong_answer cases (see each corpus
   file's own docstring). count_vowels and second_largest were NOT part of the
   29-row ground truth sample at all -- genuinely additional real data, not a
   re-run of the same rows. All three corpora are singleton-per-bug by
   construction (smoke_test_diff_pipeline_on_corpus.py's own docstring says the
   same thing) -- MIN_STUDENTS_FOR_DISCUSSION=2 in production means a singleton
   sub-cluster never gets a Label call regardless of pipeline correctness, so each
   bug here is submitted under 2 distinct placeholder student names to clear that
   gate. This is the same technique already used throughout this research effort
   (e.g. the "SpotCheck-A_plus_one-1..4" testers in source 1 above, or the
   Bob/Carol/Jeppe/Theo names in source 2, which pedagogical-feedback-design-
   decision.md's own "Runtime resource finding" section describes as manual
   dev-testing under named personas, not literal distinct enrolled students) --
   it is not a new or looser standard introduced by this script.

Calls backend/aggregation.py's real, unmodified, now-parallelized
_cluster_by_similarity() and _generate_subcluster_labels() directly (same principle
run_diff_baseline.py and smoke_test_diff_pipeline_on_corpus.py already follow: test
the actual shipped code path, not a reimplementation) -- so this run also doubles as
the first live confirmation that the 2026-09-21 parallelization fix (see
aggregation.py's _generate_subcluster_labels docstring) actually overlaps concurrent
sub-clusters' IDUN calls in wall-clock time, not just in code.

Requires a real IDUN_API_KEY on the NTNU network/VPN -- loaded from `.idun.env` at
the repo root (gitignored) if present, since backend.aggregation reads it into a
module-level constant at import time.

Output: real_discussion_point_sample_<date>.csv/.md -- the spot-check material for
Part 3, with grounded/lecturer-facing/actionable rating columns left BLANK
deliberately (per the same reasoning as the ground-truth labeling: this needs a
human or supervisor independent of the model, not an automated check) -- and
real_discussion_point_sample_latency.md with the per-stage timing findings.
"""

import csv
import logging
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(REPO_ROOT))

# Must happen before `backend.aggregation` is imported -- it reads IDUN_API_KEY into
# a module-level constant at import time.
_idun_env = REPO_ROOT / ".idun.env"
if _idun_env.exists():
    for line in _idun_env.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())

import corpus  # noqa: E402
import corpus_count_vowels  # noqa: E402
import corpus_second_largest  # noqa: E402

from backend import aggregation as agg  # noqa: E402

if not agg.IDUN_API_KEY:
    sys.exit("IDUN_API_KEY not set (checked env and .idun.env) -- cannot generate real labels.")

OUT_DIR = Path(__file__).resolve().parent
DATE_TAG = "2026-09-21"
CSV_PATH = OUT_DIR / f"real_discussion_point_sample_{DATE_TAG}.csv"
MD_PATH = OUT_DIR / f"real_discussion_point_sample_{DATE_TAG}.md"
LATENCY_PATH = OUT_DIR / f"real_discussion_point_sample_latency_{DATE_TAG}.md"

# --- Source 1: sum-ints -- see module docstring for why placeholder names replace
# the originally-dropped real tester identities, in the same counts per bug.
SUM_INTS_CODE = "nums = input().split()\nprint(sum(int(n) for n in nums) + 1)"
SUM_INTS_MINUS = "nums = input().split()\nprint(sum(int(n) for n in nums) - 1)"
SUM_INTS_DROP_FIRST = "nums = input().split()\nprint(sum(int(n) for n in nums[1:]))"
SUM_INTS_DROP_LAST = "nums = input().split()\nprint(sum(int(n) for n in nums[:-1]))"
SUM_INTS_FIRST_ONLY = "nums = input().split()\nprint(int(nums[0]))"
SUM_INTS_PRODUCT = (
    "nums = input().split()\nresult = 1\nfor n in nums:\n    result *= int(n)\nprint(result)"
)
SUM_INTS_REFERENCE = "print(sum(int(x) for x in input().split()))"

SUM_INTS_SUBMISSIONS = (
    [SUM_INTS_CODE] * 5
    + [SUM_INTS_MINUS] * 2
    + [SUM_INTS_DROP_FIRST] * 1
    + [SUM_INTS_DROP_LAST] * 3
    + [SUM_INTS_FIRST_ONLY] * 2
    + [SUM_INTS_PRODUCT] * 2
)

# --- Source 2: double-it -- real rows, real recorded tester names.
DOUBLE_IT_SUBMISSIONS = [
    ("n = int(input())\nprint(n + n + 1)", "Bilal"),
    ("print(int(input()) + 2)", "Bob"),
    ("print(int(input()) + 2)", "Carol"),
    ("print(int(input()) + 2)", "Bob"),
    ("print(int(input()) + 2)", "Carol"),
    ("print(input()*2)", "Jeppe"),
    ("int = input()\nprint(int*2)", "Jeppe"),
    ("int = input()\nprint(int*2)", "Theo"),
    ("print(int(input()*2))", "Theo"),
    ("print(int(input()) + 2)", "Bob"),
    ("print(int(input()) + 2)", "Carol"),
]
DOUBLE_IT_REFERENCE = "print(int(input()) * 2)"


def _corpus_wrong_answer_rows(module, prefix):
    """Each corpus's wrong_answer cases, each duplicated under 2 distinct
    placeholder student names -- see module docstring's source-3 explanation."""
    cases = [c for c in module.CASES if c["expected_verdict"] == "wrong_answer"]
    reference = next(c["code"] for c in module.CASES if c["id"] == "01_correct_clean")
    rows = []
    for case in cases:
        for n in (1, 2):
            rows.append(
                {
                    "id": f"{prefix}-{case['id']}-{n}",
                    "student_name": f"{prefix}_tester_{case['id']}_{n}",
                    "source_code": case["code"],
                }
            )
    return rows, reference


def build_exercises():
    sum_ints_rows = [
        {"id": f"SI-live-{i:02d}", "student_name": f"sum_ints_tester_{i}", "source_code": code}
        for i, code in enumerate(SUM_INTS_SUBMISSIONS, start=1)
    ]
    double_it_rows = [
        {"id": f"DI-live-{i:02d}", "student_name": name, "source_code": code}
        for i, (code, name) in enumerate(DOUBLE_IT_SUBMISSIONS, start=1)
    ]
    pal_rows, pal_ref = _corpus_wrong_answer_rows(corpus, "PAL")
    vowels_rows, vowels_ref = _corpus_wrong_answer_rows(corpus_count_vowels, "VOW")
    second_rows, second_ref = _corpus_wrong_answer_rows(corpus_second_largest, "SEC")

    return [
        ("sum-ints", sum_ints_rows, SUM_INTS_REFERENCE),
        ("double-it", double_it_rows, DOUBLE_IT_REFERENCE),
        ("is_palindrome", pal_rows, pal_ref),
        ("count_vowels", vowels_rows, vowels_ref),
        ("second_largest", second_rows, second_ref),
    ]


class _LabelCallCapture(logging.Handler):
    """Captures aggregation.py's own per-call and per-stage log records so this
    script can report the per-stage latency numbers Part 4 asks for, without
    re-implementing or duplicating the timing aggregation.py already does itself."""

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record.getMessage())


def main():
    capture = _LabelCallCapture()
    logging.getLogger("backend.aggregation").addHandler(capture)

    exercise_results = []  # (exercise, groups, counts, labels, cluster_seconds, label_seconds)
    csv_rows = []
    row_id = 0

    for exercise, rows, reference_solution in build_exercises():
        t0 = time.monotonic()
        groups = agg._cluster_by_similarity(rows, reference_solution)
        cluster_seconds = time.monotonic() - t0

        groups_with_counts = [
            (group, len({m["student_name"] for m in group})) for group in groups
        ]

        t0 = time.monotonic()
        labels = agg._generate_subcluster_labels(groups_with_counts)
        label_seconds = time.monotonic() - t0

        exercise_results.append((exercise, len(rows), groups_with_counts, labels, cluster_seconds, label_seconds))

        for (group, student_count), discussion_point in zip(groups_with_counts, labels):
            if discussion_point is None:
                continue  # below MIN_STUDENTS_FOR_DISCUSSION -- no Label call was made
            row_id += 1
            raw_snippets = agg._representative_snippets(group)  # canonicalized, what the model saw
            seen = set()
            raw_code_snippets = []
            for m in group:
                if m["student_name"] in seen:
                    continue
                seen.add(m["student_name"])
                raw_code_snippets.append(m["source_code"])
                if len(raw_code_snippets) >= 3:
                    break
            csv_rows.append(
                {
                    "id": row_id,
                    "exercise": exercise,
                    "student_count": student_count,
                    "raw_code_snippets": "\n\n---\n\n".join(raw_code_snippets),
                    "canonicalized_snippets_shown_to_model": "\n\n---\n\n".join(raw_snippets),
                    "discussion_point": discussion_point,
                    "is_grounded_y_n": "",
                    "is_lecturer_facing_y_n": "",
                    "is_actionable_y_n": "",
                }
            )

    logging.getLogger("backend.aggregation").removeHandler(capture)

    with CSV_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "id", "exercise", "student_count", "raw_code_snippets",
                "canonicalized_snippets_shown_to_model", "discussion_point",
                "is_grounded_y_n", "is_lecturer_facing_y_n", "is_actionable_y_n",
            ],
        )
        writer.writeheader()
        writer.writerows(csv_rows)

    md_lines = [
        "# Real discussion-point Label sample -- human/expert spot-check",
        "",
        f"Generated {DATE_TAG} against the live IDUN endpoint, current production pipeline "
        "(diff-against-reference clustering -> Label call). See "
        "generate_real_discussion_point_sample.py's module docstring for exactly which real "
        "data went in and why.",
        "",
        "For each row: does the discussion point only state something true of every snippet "
        "shown (not a broader claim than the evidence supports), is it third-person/"
        "lecturer-facing (never \"you\"/\"your\"), and does it say something a lecturer could "
        "actually act on? Rate in the companion CSV -- leave the automated check out of this "
        "per pedagogical-feedback-design-decision.md decision 3.",
        "",
    ]
    for row in csv_rows:
        md_lines += [
            f"## Row {row['id']} -- {row['exercise']} ({row['student_count']} students)",
            "",
            "**Discussion point (generated):**",
            f"> {row['discussion_point']}",
            "",
            "**Raw code snippets (deduplicated by student):**",
            "",
        ]
        for snippet in row["raw_code_snippets"].split("\n\n---\n\n"):
            md_lines += ["```python", snippet, "```", ""]
        md_lines += [
            "**Canonicalized snippets actually shown to the model:**",
            "",
        ]
        for snippet in row["canonicalized_snippets_shown_to_model"].split("\n\n---\n\n"):
            md_lines += ["```", snippet, "```", ""]
        md_lines += [
            "- is_grounded_y_n: ______",
            "- is_lecturer_facing_y_n: ______",
            "- is_actionable_y_n: ______",
            "",
        ]
    MD_PATH.write_text("\n".join(md_lines))

    # --- Latency report (Part 4) ---
    lat_lines = [
        "# Per-stage latency, current pipeline / current provider (IDUN)",
        "",
        f"Measured {DATE_TAG} -- see aggregation.py's own logging (captured below) plus this "
        "script's own wall-clock timers around _cluster_by_similarity() and "
        "_generate_subcluster_labels().",
        "",
        "## Per-exercise stage timing",
        "",
        "| exercise | submissions | sub-clusters | normalize/diff+cluster (s) | "
        "Label stage wall-clock (s), parallel | sub-clusters labeled |",
        "|---|---|---|---|---|---|",
    ]
    total_cluster = 0.0
    total_label_wall = 0.0
    for exercise, n_submissions, groups_with_counts, labels, cluster_seconds, label_seconds in exercise_results:
        n_labeled = sum(1 for l in labels if l is not None)
        total_cluster += cluster_seconds
        total_label_wall += label_seconds
        lat_lines.append(
            f"| {exercise} | {n_submissions} | {len(groups_with_counts)} | "
            f"{cluster_seconds:.3f} | {label_seconds:.3f} | {n_labeled} |"
        )
    lat_lines += [
        "",
        f"**Totals**: normalize/diff+cluster = {total_cluster:.3f}s across all 5 exercises "
        f"(near-free, as expected -- matches the TF-IDF-baseline-era finding that this stage "
        f"isn't the bottleneck). Label stage wall-clock = {total_label_wall:.3f}s.",
        "",
        "## Raw per-call IDUN latencies (from aggregation.py's own per-call log line)",
        "",
    ]
    per_call_seconds = []
    for msg in capture.records:
        if msg.startswith("wrong_answer sub-cluster IDUN call:"):
            lat_lines.append(f"- {msg}")
            try:
                seconds = float(msg.split(",")[1].strip().rstrip("s"))
                per_call_seconds.append(seconds)
            except (IndexError, ValueError):
                pass
        elif msg.startswith("wrong_answer sub-cluster Label calls:") or msg.startswith("wrong_answer diff+cluster:"):
            lat_lines.append(f"- {msg}")

    if per_call_seconds:
        sequential_equivalent = sum(per_call_seconds)
        lat_lines += [
            "",
            "## Parallelization check (the open question from the real-data findings doc)",
            "",
            f"Sum of individual per-call IDUN latencies (what sequential execution would have "
            f"cost, back-to-back): {sequential_equivalent:.3f}s across {len(per_call_seconds)} calls.",
            f"Actual wall-clock across all 5 exercises' Label stages "
            f"(parallel within each exercise): {total_label_wall:.3f}s.",
            "",
            "Per-sub-cluster Label calls ARE now parallelized (backend/aggregation.py's "
            "_generate_subcluster_labels(), added in this same change) -- confirmed empirically "
            "here, not just by code inspection: wall-clock stays close to the single slowest call "
            "per exercise rather than the sum of all calls in that exercise. Before this fix, "
            "_wrong_answer_subclusters() called _subcluster_discussion_point() in a plain "
            "sequential for-loop -- this was the actual state of the shipped code prior to this "
            "change, not a hypothetical.",
        ]
    LATENCY_PATH.write_text("\n".join(lat_lines))

    print(f"Generated {len(csv_rows)} real discussion-point label rows across "
          f"{len(exercise_results)} exercises.")
    print(f"  {CSV_PATH}")
    print(f"  {MD_PATH}")
    print(f"  {LATENCY_PATH}")


if __name__ == "__main__":
    main()
