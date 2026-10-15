"""Scores an output-signature level for wrong_answer sub-clustering against the same
29-submission ground truth (subcluster_ground_truth_sample.csv) and the same harness
(subcluster_eval.py) as run_diff_baseline.py, at the production threshold only.

Motivation: double-it-shape-vs-behavior-limitation-2026-09-21.md. Diff-against-
reference measures code *shape*; the ground truth groups by *behavior*, and
DI-01/02/05/07 print the same wrong output through three different code edits, so no
code-text signal can group them. Every graded submission already has its actual
per-test stdout stored (raw_test_results), so a behavioral signal costs no extra
execution in production.

Three variants, one variable at a time (WRONG_ANSWER_SUBCLUSTER_DISTANCE, linkage and
token pattern untouched throughout):
  (a) diff only            -- aggregation._cluster_by_similarity(), current production
  (b) signature only       -- group by aggregation._output_signature(), nothing else
  (c) signature then diff  -- aggregation._group_wrong_answers(): signature groups are
                              final unless the signature is weak (fewer than
                              MIN_TESTS_FOR_FINAL_SIGNATURE test cases), in which case
                              the diff signal splits them further

All three call aggregation.py's real functions, same as run_diff_baseline.py.

Where each submission's raw_test_results comes from: the ground-truth CSV holds code,
not results, so each submission is run here against the REAL stored test cases of the
question it was submitted to, with the same subprocess runner the reading aid used
(build_subcluster_ground_truth_io_table.run_code -- no Judge0 needed). Nothing is
fabricated:
  - sum-ints: the 'sum-ints' question row's stored test_cases (all 5, including the
    single-number "7" case the reading aid left out -- production signatures use every
    stored case, so this does too). Seeded in backend/store.py's init_db().
  - double-it: per submission, the question row it was actually submitted to in
    backend/prototype.db (see build_subcluster_ground_truth_sample.py's DB ids).
    DB ids 4-5, 9-10, 28-31, 44-45 came from double-it-2..5, which all store
    [3 -> 6, 10 -> 20]; DB id 2 ("n = int(input())\\nprint(n + n + 1)") came from the
    original 'double-it' row, which stores only [4 -> 8]. The four prints-twice
    submissions this targets (DB 28-31 = DI-01/02/05/07) are all from one question,
    double-it-4, so the case this fixes is reproduced exactly as production would see it.
  - is_palindrome: no question row exists; corpus.py's single TEST_INPUT is the only
    test input in the repo, with its expected output computed by running corpus.py's
    reference solution (same as the reading aid). Not padded with invented inputs, so
    this exercise's signature is weak by construction -- reported as such.

Each stored test case's expected_stdout is also checked against the reference
solution's own output before scoring, so a transcription slip here can't silently
produce a "better" score.

Pooling note: the ground truth pools the double-it rows across question rows into one
exercise, and run_diff_baseline.py clusters them in one call; this script does the same
for all three variants so (a) stays exactly comparable to the published 0.899. Weakness
is decided per signature (its length = that question's test count), which is the same
thing production decides per question.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

# feedback-research/ is split into folders (corpora/, clustering-eval/, ...); the
# scripts import each other across them, so all research folders go on the path.
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "corpora"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "clustering-eval"))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import corpus  # noqa: E402
from build_subcluster_ground_truth_io_table import EXERCISE_IO_CONFIG, run_code  # noqa: E402
from subcluster_eval import load_ground_truth, score_exercise, summarize  # noqa: E402

from backend import aggregation as agg  # noqa: E402

GROUND_TRUTH_CSV = Path(__file__).resolve().parent / "subcluster_ground_truth_sample.csv"

# Copied verbatim from backend/prototype.db's questions.test_cases (see module docstring).
SUM_INTS_TESTS = [
    {"stdin": "1 2 3\n", "expected_stdout": "6"},
    {"stdin": "10 20 30 40\n", "expected_stdout": "100"},
    {"stdin": "-5 5\n", "expected_stdout": "0"},
    {"stdin": "7\n", "expected_stdout": "7"},
    {"stdin": "1000000 2000000\n", "expected_stdout": "3000000"},
]
DOUBLE_IT_2_TO_5_TESTS = [  # double-it-2, -3, -4, -5 (identical on all four rows)
    {"stdin": "3\n", "expected_stdout": "6"},
    {"stdin": "10\n", "expected_stdout": "20"},
]
DOUBLE_IT_ORIGINAL_TESTS = [{"stdin": "4", "expected_stdout": "8"}]  # 'double-it'
# Only DB id 2 came from the original 'double-it' row; identified by its code, which
# no other double-it submission shares.
_DOUBLE_IT_ORIGINAL_CODE = "n = int(input())\nprint(n + n + 1)"


def _is_palindrome_tests():
    reference = EXERCISE_IO_CONFIG["is_palindrome"]["reference_solution"]
    stdin = corpus.TEST_INPUT + "\n"
    return [{"stdin": stdin, "expected_stdout": run_code(reference, stdin)}]


def tests_for(exercise, code):
    if exercise == "sum-ints":
        return SUM_INTS_TESTS
    if exercise == "double-it":
        return DOUBLE_IT_ORIGINAL_TESTS if code == _DOUBLE_IT_ORIGINAL_CODE else DOUBLE_IT_2_TO_5_TESTS
    if exercise == "is_palindrome":
        return _is_palindrome_tests()
    raise KeyError(exercise)


def raw_test_results(code, tests):
    """Same shape run_test_cases() stores (the fields _output_signature() reads),
    with Judge0's pass rule: clean exit and stripped stdout == stripped expected."""
    results = []
    for i, case in enumerate(tests):
        out = run_code(code, case["stdin"])
        if out.startswith("ERROR:"):
            # wrong_answer means it ran cleanly; a crash here would mean the sample
            # isn't what it claims to be -- stop rather than score it.
            raise RuntimeError(f"wrong_answer sample crashed on {case['stdin']!r}: {out}")
        results.append(
            {
                "case_index": i,
                "stdin": case["stdin"],
                "expected_stdout": case["expected_stdout"],
                "stdout": out + "\n",
                "passed": out == case["expected_stdout"].strip(),
            }
        )
    return json.dumps(results)


def check_reference_passes(exercise, tests):
    reference = EXERCISE_IO_CONFIG[exercise]["reference_solution"]
    for case in tests:
        got = run_code(reference, case["stdin"])
        if got != case["expected_stdout"].strip():
            raise RuntimeError(f"{exercise}: reference printed {got!r} for {case['stdin']!r}, "
                               f"stored expected {case['expected_stdout']!r}")


def variant_diff_only(rows, reference):
    return agg._cluster_by_similarity(rows, reference)


def variant_signature_only(rows, _reference):
    groups = defaultdict(list)
    for row in rows:
        groups[agg._output_signature(row)].append(row)
    return list(groups.values())


def variant_signature_then_diff(rows, reference):
    return agg._group_wrong_answers(rows, reference)


VARIANTS = [
    ("(a) diff only", variant_diff_only),
    ("(b) signature only", variant_signature_only),
    ("(c) signature then diff", variant_signature_then_diff),
]


def main():
    ground_truth = load_ground_truth(GROUND_TRUTH_CSV)
    exercises = list(ground_truth)

    rows_by_exercise = {}
    print("Output signatures (computed against each submission's own question's stored tests):")
    for exercise, submissions in ground_truth.items():
        rows = []
        for sid, (code, bug_group) in submissions.items():
            tests = tests_for(exercise, code)
            check_reference_passes(exercise, tests)
            row = {"id": sid, "source_code": code, "raw_test_results": raw_test_results(code, tests)}
            rows.append(row)
            print(f"  {sid:>7} {bug_group:<22} {agg._output_signature(row)}")
        rows_by_exercise[exercise] = rows

    print(f"\nProduction threshold WRONG_ANSWER_SUBCLUSTER_DISTANCE={agg.WRONG_ANSWER_SUBCLUSTER_DISTANCE}, "
          f"MIN_TESTS_FOR_FINAL_SIGNATURE={agg.MIN_TESTS_FOR_FINAL_SIGNATURE}")
    print("format: ari (predicted_groups/true_groups)\n")
    header = f"{'variant':<24} | " + " | ".join(f"{ex:^16}" for ex in exercises) + " | mean ARI | mean P | mean R"
    print(header)
    print("-" * len(header))

    scores = {}
    for name, fn in VARIANTS:
        per_exercise = {}
        for exercise in exercises:
            true_labels = {sid: bg for sid, (_c, bg) in ground_truth[exercise].items()}
            reference = EXERCISE_IO_CONFIG[exercise]["reference_solution"]
            groups = fn(rows_by_exercise[exercise], reference)
            per_exercise[exercise] = score_exercise([[r["id"] for r in g] for g in groups], true_labels)
        mean = summarize(per_exercise)
        scores[name] = (per_exercise, mean)
        cells = " | ".join(
            f"{per_exercise[ex]['ari']:>6.3f} ({per_exercise[ex]['n_predicted_groups']:>2}/{per_exercise[ex]['n_true_groups']:>2})"
            for ex in exercises
        )
        print(f"{name:<24} | {cells} | {mean['ari']:>8.3f} | {mean['precision']:.3f} | {mean['recall']:.3f}")

    print("\nPairwise precision/recall per exercise:")
    for name, (per_exercise, _mean) in scores.items():
        print(f"  {name}")
        for exercise in exercises:
            s = per_exercise[exercise]
            print(f"    {exercise:>14}: P={s['precision']:.3f} R={s['recall']:.3f} F1={s['f1']:.3f} "
                  f"(tp={s['tp']} fp={s['fp']} fn={s['fn']})")

    a = scores["(a) diff only"][1]["ari"]
    c = scores["(c) signature then diff"][1]["ari"]
    verdict = "(c) >= (a): switch is justified" if c >= a else "(c) < (a): keep production unchanged"
    print(f"\nDecision rule, mean ARI: (a) {a:.3f} vs (c) {c:.3f} -> {verdict}")


if __name__ == "__main__":
    main()
