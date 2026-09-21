"""Runs a diff-against-reference-solution sub-clustering signal through
subcluster_eval's harness, at the same threshold sweep run_tfidf_baseline.py used,
against the same 29-submission ground truth -- a directly comparable second data
point to that TF-IDF-on-raw-code baseline.

Motivation (see run_tfidf_baseline.py's results): TF-IDF over canonicalized raw code
scored a mean ARI of 0.579 at the current production threshold (0.05), and even its
best-fit threshold (0.02, mean ARI 0.933) only won by over-splitting double-it's
three same-bug code shapes into separate clusters -- it measures code shape, not
behavior, while the ground truth is grouped by behavior (what's actually wrong).
This script does NOT retune that threshold further; it swaps the INPUT
REPRESENTATION -- diff-against-reference instead of raw canonicalized code -- while
keeping the exact same clustering machinery (TF-IDF vectorize -> cosine distance ->
AgglomerativeClustering, no fixed k, same token pattern and linkage constants
backend/aggregation.py already uses), so the comparison against the TF-IDF baseline
is apples-to-apples on everything except that one swap.

How the diff representation is built (see _diff_tokens()): both the submission's
code and the exercise's reference solution are canonicalized with
aggregation._canonicalize() -- the SAME identifier-renaming step the TF-IDF baseline
uses, so variable naming still doesn't matter here either. The two canonicalized
token sequences are then diffed with difflib.SequenceMatcher (token-level, not
line-level -- these are mostly one-line solutions, so a line-level diff would be too
coarse to see anything). Every token in an "equal" block (i.e. boilerplate shared
with the reference) is dropped entirely; every token from a "delete"/"insert"/
"replace" block is kept, tagged with DEL: or INS: so an omission and an addition of
the same token don't collide. That tagged token sequence -- not the submission's
full code -- is what gets TF-IDF-vectorized and clustered. autojunk is disabled on
the SequenceMatcher: its heuristic assumes large files and can misbehave on these
short token sequences with a lot of legitimately-repeated tokens (parens, `input`,
`print`, ...).

Reference solutions are NOT re-derived here -- imported from
build_subcluster_ground_truth_io_table.py's EXERCISE_IO_CONFIG, the same "one source
of truth per exercise" reference solutions already used to compute expected output
for the .md reading aid, so there's exactly one place in this whole eval effort where
each exercise's reference solution is defined.

2026-09-21 update: this diff-against-reference signal has since BECOME production
(backend/aggregation.py's _cluster_by_similarity() and the new _diff_tokens() helper
it added -- see that module's docstring). This script now calls those functions
directly rather than a parallel copy, so a harness run here is testing the actual
shipped code path, not a re-implementation that could silently drift from it.
WRONG_ANSWER_SUBCLUSTER_DISTANCE is swapped per threshold for the duration of each
call only (it's a plain module global _cluster_by_similarity reads fresh every
call) and restored immediately after -- doesn't touch the production 0.05 value,
the ground-truth CSV, or anything else, same as run_tfidf_baseline.py's approach
when it was still calling into aggregation.py this same way.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from subcluster_eval import load_ground_truth, score_exercise, summarize  # noqa: E402
from build_subcluster_ground_truth_io_table import EXERCISE_IO_CONFIG  # noqa: E402

from backend import aggregation as agg  # noqa: E402

GROUND_TRUTH_CSV = Path(__file__).resolve().parent / "subcluster_ground_truth_sample.csv"
THRESHOLDS = [0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4]  # same sweep as run_tfidf_baseline.py


def run_clustering_at_threshold(exercise_submissions, reference_solution, threshold):
    """exercise_submissions: {submission_id: (code, bug_group)}. Returns predicted
    groups as a list of lists of submission_ids, using aggregation.py's real,
    now-production _cluster_by_similarity()/_diff_tokens()."""
    rows = [
        {"id": sid, "source_code": code}
        for sid, (code, _bug_group) in exercise_submissions.items()
    ]
    original = agg.WRONG_ANSWER_SUBCLUSTER_DISTANCE
    agg.WRONG_ANSWER_SUBCLUSTER_DISTANCE = threshold
    try:
        groups = agg._cluster_by_similarity(rows, reference_solution)
    finally:
        agg.WRONG_ANSWER_SUBCLUSTER_DISTANCE = original
    return [[row["id"] for row in group] for group in groups]


def main():
    ground_truth = load_ground_truth(GROUND_TRUTH_CSV)
    exercises = list(ground_truth)

    print("Diff-against-reference signal -- ARI per exercise at each threshold")
    print("format: ari (predicted_groups/true_groups); predicted > true = over-splitting, "
          "predicted < true = over-merging.\n")

    header = f"{'threshold':>9} | " + " | ".join(f"{ex:^20}" for ex in exercises) + " | mean ARI"
    print(header)
    print("-" * len(header))

    all_results = []
    for threshold in THRESHOLDS:
        per_exercise = {}
        for exercise, submissions in ground_truth.items():
            true_labels = {sid: bug_group for sid, (_code, bug_group) in submissions.items()}
            reference_solution = EXERCISE_IO_CONFIG[exercise]["reference_solution"]
            predicted = run_clustering_at_threshold(submissions, reference_solution, threshold)
            per_exercise[exercise] = score_exercise(predicted, true_labels)
        mean = summarize(per_exercise)
        all_results.append((threshold, per_exercise, mean))

        cells = " | ".join(
            f"{per_exercise[ex]['ari']:>6.3f} ({per_exercise[ex]['n_predicted_groups']:>2}/{per_exercise[ex]['n_true_groups']:>2})"
            for ex in exercises
        )
        print(f"{threshold:>9} | {cells} | {mean['ari']:>7.3f}")

    print("\nPairwise precision/recall/F1 per exercise at each threshold:")
    for threshold, per_exercise, _mean in all_results:
        print(f"\n  threshold={threshold}")
        for exercise in exercises:
            s = per_exercise[exercise]
            print(
                f"    {exercise:>14}: P={s['precision']:.3f} R={s['recall']:.3f} F1={s['f1']:.3f}"
            )

    print("\nSpecific checks:")
    for threshold, per_exercise, _mean in all_results:
        di = per_exercise["double-it"]
        pal = per_exercise["is_palindrome"]
        print(
            f"  threshold={threshold}: double-it ARI={di['ari']:.3f} "
            f"({di['n_predicted_groups']}/{di['n_true_groups']} groups) | "
            f"is_palindrome ARI={pal['ari']:.3f} ({pal['n_predicted_groups']}/{pal['n_true_groups']} groups)"
        )


if __name__ == "__main__":
    main()
