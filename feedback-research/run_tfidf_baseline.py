"""Runs raw-canonicalized-code TF-IDF + agglomerative clustering -- what
backend/aggregation.py's wrong_answer sub-clustering did BEFORE the 2026-09-21
diff-against-reference switch (see that module's docstring) -- through
subcluster_eval's harness, at a spread of distance thresholds, against the
hand-labeled ground truth in subcluster_ground_truth_sample.csv.

This was the first harness run: a real number for how the pre-switch approach did
against real ground truth, instead of the qualitative "everything merged"
observation that motivated it. Its results (mean ARI 0.579 at the then-and-still
production threshold 0.05, is_palindrome specifically at 0.000) are cited directly
in aggregation.py's 2026-09-21 docstring entry as the "before" side of that switch,
so this script is now a standalone, self-contained re-implementation (it does NOT
call aggregation._cluster_by_similarity, whose input representation has since
changed to diff-against-reference) -- kept independent of production on purpose, so
this baseline stays reproducible even as production moves on. Only _canonicalize()
and _TOKEN_PATTERN are still imported from aggregation.py, since those two are
unrelated to which signal (raw code vs. diff) gets vectorized.

Deliberately does NOT touch discussion-point generation
(_wrong_answer_subclusters/_subcluster_discussion_point, the IDUN/Ollama call) --
per the findings doc, reviewing discussion points on sub-clusters that aren't
correctly separated in the first place isn't informative. This only exercises the
clustering step in isolation, so it needs no network access and no IDUN_API_KEY.

Only the distance threshold is varied here. token_pattern (r"\S+") and linkage
("complete") match whatever backend/aggregation.py had them set to as of the
2026-09-16 retune.
"""

import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import TfidfVectorizer

from subcluster_eval import load_ground_truth, score_exercise, summarize  # noqa: E402

from backend import aggregation as agg  # noqa: E402

GROUND_TRUTH_CSV = Path(__file__).resolve().parent / "subcluster_ground_truth_sample.csv"
THRESHOLDS = [0.02, 0.05, 0.1, 0.15, 0.2, 0.3, 0.4]


def cluster_by_raw_code_similarity(rows: list, threshold: float) -> list:
    """Standalone re-implementation of what aggregation._cluster_by_similarity()
    did before the 2026-09-21 switch: TF-IDF over each submission's own raw
    canonicalized code (no reference solution involved at all), agglomerative
    clustering on cosine distance, no fixed k."""
    if len(rows) < 2:
        return [[r] for r in rows]
    canon = [agg._canonicalize(r["source_code"]) for r in rows]
    try:
        matrix = TfidfVectorizer(token_pattern=agg._TOKEN_PATTERN).fit_transform(canon)
    except ValueError:
        return [[r] for r in rows]
    if matrix.shape[1] == 0:
        return [[r] for r in rows]
    labels = AgglomerativeClustering(
        n_clusters=None, distance_threshold=threshold, metric="cosine", linkage="complete",
    ).fit_predict(matrix.toarray())
    groups = defaultdict(list)
    for row, label in zip(rows, labels):
        groups[int(label)].append(row)
    return list(groups.values())


def run_clustering_at_threshold(exercise_submissions, threshold):
    """exercise_submissions: {submission_id: (code, bug_group)}. Returns predicted
    groups as a list of lists of submission_ids."""
    rows = [
        {"id": sid, "source_code": code, "student_name": sid}
        for sid, (code, _bug_group) in exercise_submissions.items()
    ]
    groups = cluster_by_raw_code_similarity(rows, threshold)
    return [[row["id"] for row in group] for group in groups]


def main():
    ground_truth = load_ground_truth(GROUND_TRUTH_CSV)
    exercises = list(ground_truth)

    print("ARI per exercise at each threshold -- format: ari (predicted_groups/true_groups)")
    print("predicted > true means over-splitting; predicted < true means over-merging.\n")

    header = f"{'threshold':>9} | " + " | ".join(f"{ex:^20}" for ex in exercises) + " | mean ARI"
    print(header)
    print("-" * len(header))

    all_results = []
    for threshold in THRESHOLDS:
        per_exercise = {}
        for exercise, submissions in ground_truth.items():
            true_labels = {sid: bug_group for sid, (_code, bug_group) in submissions.items()}
            predicted = run_clustering_at_threshold(submissions, threshold)
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


if __name__ == "__main__":
    main()
