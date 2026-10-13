"""Builds the manual-labeling sample for wrong_answer sub-clustering ground truth.

Per semantic-subclustering-real-data-findings (aggregation.py's 2026-09-16 module
docstring): TF-IDF/agglomerative sub-clustering merged every real wrong_answer case
on is_palindrome and count_vowels into one group. Before tuning the threshold or
trying a different similarity signal further, we need labeled ground truth to score
against -- this script assembles that labeling sample, it does not do any clustering
itself.

Three real sources, no fabricated submissions:

1. sum-ints: real submissions from the live /api/submit -> Ollama sub-clustering run
   documented in discussion-point-live-verification-findings-2026-09-16.md and
   discussion-point-spotcheck-2026-09-16.csv. These rows are no longer in
   backend/prototype.db (that DB has since been reset/reused for dev testing), so
   they're transcribed verbatim from the CSV's source_snippets column, which is the
   only surviving record of them. Student names originally encoded the intended bug
   family (e.g. "SpotCheck-A_plus_one-3") -- deliberately NOT carried into this sample,
   since that would hand the labeler the answer. The two degenerate "int"-only
   submissions (Jo, karl) are excluded: not a real attempt at the exercise, just
   test noise, and including them would add a non-bug row with nothing to group.

2. double-it: real submissions still in backend/prototype.db today, transcribed
   verbatim (see the query this was built from). These accumulated across
   double-it/double-it-2/.../double-it-5 -- the same exercise recreated several
   times during manual dev testing (see simulate_lecture.py), not five different
   exercises -- so they're pooled here as one exercise for labeling purposes.

3. is_palindrome: the three wrong_answer cases in corpus.py (ids 03-05). These are
   hand-written representative bugs (see corpus.py's own docstring: a rebuild from a
   documented spec, not literal student submissions), so unlike the other two
   exercises there's only one submission per bug -- no repeated-student structure to
   test recall on for this exercise, only whether an approach avoids merging distinct
   bugs. Included anyway because the user's request named corpus.py directly as a
   source and it's genuinely real-bug-representative, just thin on volume.

Output: subcluster_ground_truth_sample.csv (submission_id, exercise, source, code,
bug_group -- bug_group blank, for hand labeling) and a companion .md with the same
submissions rendered as readable code blocks, since multi-line code in spreadsheet
cells is unpleasant to actually read.

Rows are shuffled (fixed seed) within each exercise so adjacency doesn't hint at
grouping.
"""

import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import corpus  # noqa: E402  (sys.path setup above -- feedback-research/ isn't a package, hyphen in the dir name)

OUT_DIR = Path(__file__).resolve().parent
CSV_PATH = OUT_DIR / "subcluster_ground_truth_sample.csv"
MD_PATH = OUT_DIR / "subcluster_ground_truth_sample.md"

# --- Source 1: sum-ints, real live-pipeline submissions, transcribed from
# discussion-point-spotcheck-2026-09-16.csv rows 1, 2, 15, 16 (student names with
# their bug-revealing SpotCheck-* labels intentionally dropped here).
SUM_INTS_CODE = 'nums = input().split()\nprint(sum(int(n) for n in nums) + 1)'
SUM_INTS_MINUS = 'nums = input().split()\nprint(sum(int(n) for n in nums) - 1)'
SUM_INTS_DROP_FIRST = 'nums = input().split()\nprint(sum(int(n) for n in nums[1:]))'
SUM_INTS_DROP_LAST = 'nums = input().split()\nprint(sum(int(n) for n in nums[:-1]))'
SUM_INTS_FIRST_ONLY = 'nums = input().split()\nprint(int(nums[0]))'
SUM_INTS_PRODUCT = 'nums = input().split()\nresult = 1\nfor n in nums:\n    result *= int(n)\nprint(result)'

SUM_INTS_SUBMISSIONS = (
    [SUM_INTS_CODE] * 5  # 4x SpotCheck-A_plus_one + 1x "Mock Tester - Wrong Answer"
    + [SUM_INTS_MINUS] * 2  # SpotCheck-E_minus_one-1/2
    + [SUM_INTS_DROP_FIRST] * 1  # SpotCheck-F_drop_first-1
    + [SUM_INTS_DROP_LAST] * 3  # SpotCheck-B_drop_last-1/2/3
    + [SUM_INTS_FIRST_ONLY] * 2  # SpotCheck-D_first_only-1/2
    + [SUM_INTS_PRODUCT] * 2  # SpotCheck-C_product-1/2
)

# --- Source 2: double-it, real rows still in backend/prototype.db today
# (question_id LIKE 'double-it%', exec_verdict='wrong_answer'), pooled across
# double-it/.../double-it-5 -- see module docstring.
DOUBLE_IT_SUBMISSIONS = [
    "n = int(input())\nprint(n + n + 1)",  # id 2, Bilal
    "print(int(input()) + 2)",  # id 4, Bob
    "print(int(input()) + 2)",  # id 5, Carol
    "print(int(input()) + 2)",  # id 9, Bob
    "print(int(input()) + 2)",  # id 10, Carol
    "print(input()*2)",  # id 28, Jeppe
    "int = input()\nprint(int*2)",  # id 29, Jeppe
    "int = input()\nprint(int*2)",  # id 30, Theo
    "print(int(input()*2))",  # id 31, Theo
    "print(int(input()) + 2)",  # id 44, Bob
    "print(int(input()) + 2)",  # id 45, Carol
]

# --- Source 3: is_palindrome, real wrong_answer cases straight from corpus.py.
IS_PALINDROME_SUBMISSIONS = [
    case["code"] for case in corpus.CASES if case["expected_verdict"] == "wrong_answer"
]

EXERCISES = [
    ("sum-ints", "SI", "live_pipeline_run_2026-09-16", SUM_INTS_SUBMISSIONS),
    ("double-it", "DI", "dev_db_prototype.db", DOUBLE_IT_SUBMISSIONS),
    ("is_palindrome", "PAL", "corpus.py_handwritten", IS_PALINDROME_SUBMISSIONS),
]


def build_rows():
    rng = random.Random(42)
    rows = []
    for exercise, prefix, source, submissions in EXERCISES:
        shuffled = list(submissions)
        rng.shuffle(shuffled)
        for i, code in enumerate(shuffled, start=1):
            rows.append(
                {
                    "submission_id": f"{prefix}-{i:02d}",
                    "exercise": exercise,
                    "source": source,
                    "code": code,
                    "bug_group": "",
                }
            )
    return rows


def write_csv(rows):
    with CSV_PATH.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["submission_id", "exercise", "source", "code", "bug_group"])
        writer.writeheader()
        writer.writerows(rows)


def write_md(rows):
    lines = [
        "# Wrong-answer sub-clustering: ground truth labeling sample",
        "",
        "For each exercise below, fill in `bug_group` in the companion CSV "
        "(`subcluster_ground_truth_sample.csv`) for every submission id: submissions "
        "that share the same underlying bug get the same group label (e.g. `off-by-one`, "
        "`missing-lower`, `g1`, whatever's convenient) within that exercise. Group labels "
        "only need to be consistent within an exercise, not across exercises.",
        "",
    ]
    current_exercise = None
    for row in rows:
        if row["exercise"] != current_exercise:
            current_exercise = row["exercise"]
            lines.append(f"## {current_exercise}")
            lines.append("")
        lines.append(f"### {row['submission_id']}")
        lines.append("")
        lines.append("```python")
        lines.append(row["code"])
        lines.append("```")
        lines.append("")
        lines.append("bug_group: ______")
        lines.append("")
    MD_PATH.write_text("\n".join(lines))


def main():
    rows = build_rows()
    write_csv(rows)
    write_md(rows)
    print(f"Wrote {len(rows)} submissions across {len(EXERCISES)} exercises.")
    print(f"  {CSV_PATH}")
    print(f"  {MD_PATH}")


if __name__ == "__main__":
    main()
