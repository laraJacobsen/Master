"""Smoke test for the 2026-09-21 diff-against-reference switch in
backend/aggregation.py (_cluster_by_similarity/_diff_tokens), run before calling that
switch done.

The 29-submission ground truth sample only covers 3 exercises (sum-ints, double-it,
is_palindrome), and feedback-research/corpus.py's own wrong_answer cases (3, all
already in that sample as PAL-01/02/03) don't add any new coverage on their own. This
script instead runs the new production clustering function against the wrong_answer
cases in ALL THREE corpus_*.py files -- is_palindrome (corpus.py), count_vowels
(corpus_count_vowels.py), and second_largest (corpus_second_largest.py) -- so
count_vowels and second_largest, never exercised by either harness run so far, get
run through the actual switched-over pipeline at least once before this is called
done.

Each corpus file's wrong_answer cases are deliberately hand-written to be distinct
bugs (see each file's own docstring/comments -- e.g. corpus_second_largest.py's
"wrong_no_dedup" vs "wrong_ascending_confusion" vs "wrong_flipped_comparison"), one
submission per bug, no repeats. That's not enough to score recall (same limitation as
is_palindrome's 3 singletons in the labeled sample), but it IS enough to check two
things mechanically: (1) the pipeline doesn't crash on exercises/code it's never seen,
and (2) it doesn't grossly over-merge cases that are known-by-construction to be
distinct bugs (the exact failure mode this whole switch was meant to fix).

Calls backend/aggregation.py's real _cluster_by_similarity()/_diff_tokens() directly,
same as run_diff_baseline.py -- not a re-implementation.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import corpus  # noqa: E402
import corpus_count_vowels  # noqa: E402
import corpus_second_largest  # noqa: E402

from backend import aggregation as agg  # noqa: E402

EXERCISES = [
    ("is_palindrome", corpus),
    ("count_vowels", corpus_count_vowels),
    ("second_largest", corpus_second_largest),
]


def main():
    any_failures = False

    for exercise_name, module in EXERCISES:
        wrong_answer_cases = [c for c in module.CASES if c["expected_verdict"] == "wrong_answer"]
        reference_solution = next(
            c["code"] for c in module.CASES if c["id"] == "01_correct_clean"
        )
        rows = [
            {"id": c["id"], "source_code": c["code"], "student_name": c["id"]}
            for c in wrong_answer_cases
        ]

        print(f"\n=== {exercise_name}: {len(rows)} wrong_answer cases (each a distinct "
              f"hand-written bug, by construction) ===")

        try:
            groups = agg._cluster_by_similarity(rows, reference_solution)
        except Exception as e:  # noqa: BLE001 -- smoke test: report, don't hide
            print(f"  CRASHED: {type(e).__name__}: {e}")
            any_failures = True
            continue

        print(f"  -> {len(groups)} predicted group(s) from {len(rows)} known-distinct bugs")
        for group in groups:
            ids = [row["id"] for row in group]
            flag = "  <-- MERGED DISTINCT BUGS" if len(ids) > 1 else ""
            print(f"    {ids}{flag}")
            if len(ids) > 1:
                any_failures = True

    print()
    if any_failures:
        print("SMOKE TEST: issues found (see CRASHED / MERGED lines above).")
    else:
        print("SMOKE TEST: no crashes, no known-distinct bugs merged together.")


if __name__ == "__main__":
    main()
