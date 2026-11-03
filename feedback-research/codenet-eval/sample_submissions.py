"""Step 2 of the CodeNet classifier eval: draw a stratified sample of submissions
for the problems in problems.csv (see select_problems.py).

Up to --per-cell submissions per (problem x language x status), drawn with a fixed
seed, so the sample is reproducible and every scored status is represented even
where it's rare (Memory Limit Exceeded is ~1% of submissions). Same filters as
select_problems.py: C, Java and Python 3 only, scored statuses only. A submission is
only eligible if its source file was actually extracted under data/.

Writes sample.csv next to this script: CodeNet ids and metadata only, no code --
run_judge0.py reads the code from CODENET_DIR at run time.

Also checks select_problems.py's assumption that AIZU's bare "Python" is Python 2:
an accepted submission compiled under this machine's Python 3 should almost never
raise SyntaxError if it was written for Python 3, and often will if it was written
for Python 2 (print statements, `except E, e`, ...). Accepted Python3 submissions
are compiled the same way as the baseline.

Usage:
    python feedback-research/codenet-eval/sample_submissions.py
    python feedback-research/codenet-eval/sample_submissions.py --per-cell 10
"""

import argparse
import csv
import random
import warnings
from collections import Counter

from select_problems import CODENET_DIR, HERE, LANGUAGES, STATUSES, python_major

SEED = 20261019


def source_path(row: dict):
    return CODENET_DIR / "data" / row["problem_id"] / row["language"] / \
        f"{row['submission_id']}.{row['filename_ext']}"


def py3_syntax_error_rate(rows: list, rng: random.Random, n: int = 200):
    """Share of `rows` (sampled down to n) that fail to compile as Python 3."""
    rows = rng.sample(rows, min(n, len(rows)))
    failed = 0
    for row in rows:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")  # old code trips invalid-escape warnings
                compile(source_path(row).read_bytes(), str(source_path(row)), "exec")
        except (SyntaxError, ValueError):
            failed += 1
    return failed, len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--per-cell", type=int, default=20,
                        help="max submissions per (problem, language, status)")
    args = parser.parse_args()

    with open(HERE / "problems.csv", newline="", encoding="utf-8") as f:
        problem_ids = [p["id"] for p in csv.DictReader(f)]

    rng = random.Random(SEED)
    sample = []
    missing_files = 0
    bare_python_ac, python3_ac = [], []
    for pid in problem_ids:
        cells = {}
        with open(CODENET_DIR / "metadata" / f"{pid}.csv", newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["language"] not in LANGUAGES or row["status"] not in STATUSES:
                    continue
                if not source_path(row).is_file():
                    missing_files += 1
                    continue
                if row["language"] == "Python":
                    major = python_major(row["original_language"])
                    if row["status"] == "Accepted" and major == 3:
                        python3_ac.append(row)
                    elif row["status"] == "Accepted" and major is None:
                        bare_python_ac.append(row)
                    if major != 3:
                        continue
                cells.setdefault((row["language"], row["status"]), []).append(row)
        for key in sorted(cells):
            rows = sorted(cells[key], key=lambda r: r["submission_id"])
            sample.extend(rng.sample(rows, min(args.per_cell, len(rows))))

    fields = ["submission_id", "problem_id", "language", "original_language", "status",
              "filename_ext", "cpu_time", "memory", "code_size", "accuracy"]
    out_path = HERE / "sample.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sample)

    print(f"Wrote {len(sample)} submissions to {out_path}")
    if missing_files:
        print(f"({missing_files} metadata rows skipped: source file not extracted)")

    counts = Counter((r["language"], r["status"]) for r in sample)
    width = max(len(s) for s in STATUSES)
    print(f"\n{'':{width}}  " + "  ".join(f"{lang:>6}" for lang in LANGUAGES))
    for status in STATUSES:
        print(f"{status:{width}}  " + "  ".join(f"{counts[(lang, status)]:>6}" for lang in LANGUAGES))
    print(f"(max {args.per_cell * len(problem_ids)} per cell: {args.per_cell} x {len(problem_ids)} problems)")

    print("\nCompiles as Python 3? (accepted submissions, SyntaxError rate)")
    for label, rows in [("Python3 (baseline)", python3_ac), ('bare "Python"', bare_python_ac)]:
        if rows:
            failed, n = py3_syntax_error_rate(rows, rng)
            print(f"  {label}: {failed}/{n} fail ({failed / n:.0%})")


if __name__ == "__main__":
    main()
