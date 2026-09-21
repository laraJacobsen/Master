"""Reusable evaluation harness for wrong_answer sub-clustering: scores any clustering
result against the hand-labeled ground truth in subcluster_ground_truth_sample.csv.

Metrics: adjusted Rand index (ARI) -- the standard "does this clustering agree with
hand-labeled groups" metric -- and pairwise precision/recall/F1 on "should these two
submissions be in the same group" pairs, which is more interpretable when ARI's scale
(can go negative, 1.0 = perfect agreement, ~0.0 = chance) feels opaque.

bug_group labels are only meaningful *within* one exercise (see
build_subcluster_ground_truth_sample.py's docstring) -- never compare submissions
across exercises. All scoring here is per-exercise; summarize() averages across
exercises for a single headline number, but the per-exercise numbers are what
actually diagnoses anything.

This module only scores a clustering result against ground truth; it doesn't run any
clustering algorithm itself. See run_tfidf_baseline.py for the first caller.
"""

import csv
from collections import defaultdict
from itertools import combinations

from sklearn.metrics import adjusted_rand_score


def load_ground_truth(csv_path):
    """Returns {exercise: {submission_id: (code, bug_group)}}. Rows with an empty
    bug_group are excluded rather than guessed at."""
    by_exercise = defaultdict(dict)
    with open(csv_path, newline="") as f:
        for row in csv.DictReader(f):
            if not row["bug_group"]:
                continue
            by_exercise[row["exercise"]][row["submission_id"]] = (row["code"], row["bug_group"])
    return dict(by_exercise)


def pairwise_precision_recall_f1(predicted_groups, true_labels):
    """predicted_groups: list of lists of submission_ids (one predicted cluster
    each -- singletons are fine). true_labels: {submission_id: bug_group}. Scores
    over every pair of ids appearing in true_labels."""
    ids = list(true_labels.keys())
    pred_group_of = {}
    for gi, group in enumerate(predicted_groups):
        for sid in group:
            pred_group_of[sid] = gi

    tp = fp = fn = tn = 0
    for a, b in combinations(ids, 2):
        same_true = true_labels[a] == true_labels[b]
        same_pred = pred_group_of.get(a) == pred_group_of.get(b)
        if same_true and same_pred:
            tp += 1
        elif same_pred and not same_true:
            fp += 1
        elif same_true and not same_pred:
            fn += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1, "tp": tp, "fp": fp, "fn": fn, "tn": tn}


def score_exercise(predicted_groups, true_labels):
    """One exercise's worth. predicted_groups: list of lists of submission_ids --
    must cover every id in true_labels (raises if not). Returns ARI, pairwise
    P/R/F1, and predicted/true cluster counts (a quick over-merge/over-split
    signal on their own, before even looking at ARI)."""
    ids = list(true_labels.keys())
    pred_group_of = {}
    for gi, group in enumerate(predicted_groups):
        for sid in group:
            pred_group_of[sid] = gi
    missing = [i for i in ids if i not in pred_group_of]
    if missing:
        raise ValueError(f"predicted_groups is missing labeled ids: {missing}")

    true_seq = [true_labels[i] for i in ids]
    pred_seq = [pred_group_of[i] for i in ids]
    ari = adjusted_rand_score(true_seq, pred_seq)
    pr = pairwise_precision_recall_f1(predicted_groups, true_labels)
    return {
        "ari": ari,
        **pr,
        "n_true_groups": len(set(true_seq)),
        "n_predicted_groups": len(set(pred_seq)),
        "n_submissions": len(ids),
    }


def summarize(per_exercise_scores):
    """Unweighted mean across exercises of each metric -- one headline number.
    Unweighted so the 15-submission exercise doesn't drown out the 3-submission
    one; per-exercise scores (not this average) are what actually diagnoses
    anything."""
    keys = ["ari", "precision", "recall", "f1"]
    n = len(per_exercise_scores)
    return {k: sum(s[k] for s in per_exercise_scores.values()) / n for k in keys}
