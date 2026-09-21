"""Builds a mechanical input/output reading aid for the wrong_answer sub-clustering
ground-truth labeling sample (subcluster_ground_truth_sample.csv/.md).

Purpose: labeling 29 submissions by reading code line by line is slow. This script
instead actually RUNS each submission's code against a few of the exercise's own
known-good sample inputs and records what it actually printed, so mismatches against
the expected output show up as different values in the same column -- no code
reading, no interpretation, no grouping. That judgment call stays with the human
labeler; this script only reports what code produced.

Where "correct" comes from (one source of truth per exercise, not a second
hand-written implementation):
  - sum-ints: reference_solution + test_cases already stored on the 'sum-ints'
    question row in backend/prototype.db (seeded in backend/store.py's init_db()).
  - double-it: pooled across the double-it/double-it-2/.../double-it-5 question
    rows in backend/prototype.db (same exercise, recreated several times during dev
    testing -- see build_subcluster_ground_truth_sample.py, which pools the same
    rows' submissions the same way). double-it-2..5 share reference_solution
    "print(int(input()) * 2)" and test_cases [3->6, 10->20]; the original 'double-it'
    row used the equivalent "print(2 * int(input()))" and test case 4->8. Pooling the
    distinct stdins across all of them gives 3 sample inputs from data that already
    exists, instead of inventing new ones.
  - is_palindrome: corpus.py's own "01_correct_clean" case (the hand-written correct
    implementation already living there) and its TEST_INPUT. corpus.py only defines
    ONE test input for this exercise (TEST_INPUT = "Race car") -- there's no second,
    third, or fourth Judge0 test case for is_palindrome anywhere in this repo. Per
    the instruction to reuse existing test cases rather than invent new ones, this
    exercise's table has exactly 1 input column, not 3-4. Flagged here rather than
    silently padded with made-up inputs.

For every exercise, "expected" output is computed by actually running that
exercise's reference solution through this same subprocess runner -- not by trusting
the stored expected_stdout strings -- so the reference solution's code is the only
source of truth and the expected/actual rows are produced by an identical mechanism.

Reuses the exact same 29 submissions/ids as build_subcluster_ground_truth_sample.py
(imported, same fixed shuffle seed) -- this is a companion reading aid, not a second
sample. Does not touch bug_group anywhere.
"""

import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import corpus  # noqa: E402
from build_subcluster_ground_truth_sample import build_rows  # noqa: E402

OUT_PATH = Path(__file__).resolve().parent / "subcluster_ground_truth_io_table.md"

TIMEOUT_S = 3.0

# --- Per-exercise reference solution + sample inputs, all pulled from existing
# stored config (see module docstring for exactly where each one comes from).
EXERCISE_IO_CONFIG = {
    "sum-ints": {
        "reference_solution": "print(sum(int(x) for x in input().split()))",
        # From the 'sum-ints' question row's stored test_cases; the "7\n" case is
        # deliberately left out here -- it's a single-number input, and smoke_test.py
        # already notes that a couple of the real sum-ints test cases coincidentally
        # give the same answer for sum vs. product on single-number input, which
        # would make one column look falsely non-discriminating.
        "sample_inputs": ["1 2 3\n", "10 20 30 40\n", "-5 5\n", "1000000 2000000\n"],
    },
    "double-it": {
        "reference_solution": "print(int(input()) * 2)",
        # Pooled distinct stdins across all double-it/double-it-2../double-it-5
        # question rows (see module docstring).
        "sample_inputs": ["4\n", "3\n", "10\n"],
    },
    "is_palindrome": {
        "reference_solution": next(
            case["code"] for case in corpus.CASES if case["id"] == "01_correct_clean"
        ),
        # Only test input corpus.py defines for this exercise -- see module docstring.
        "sample_inputs": [corpus.TEST_INPUT + "\n"],
    },
}


def run_code(code: str, stdin_text: str, timeout: float = TIMEOUT_S) -> str:
    """Runs `code` as a standalone script with `stdin_text` on stdin. Returns
    stripped stdout on a clean exit, or "ERROR: <ExceptionType>" (or "ERROR: Timeout")
    otherwise -- never raises, so one bad submission can't block the batch."""
    try:
        proc = subprocess.run(
            [sys.executable, "-c", code],
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return "ERROR: Timeout"
    if proc.returncode != 0:
        return f"ERROR: {_extract_exception_type(proc.stderr)}"
    return proc.stdout.strip()


def _extract_exception_type(stderr: str) -> str:
    lines = [l for l in (stderr or "").strip().splitlines() if l.strip()]
    if not lines:
        return "UnknownError (no stderr)"
    last = lines[-1]
    match = re.match(r"^([A-Za-z_][\w.]*)\s*:", last)
    return match.group(1) if match else last[:60]


def build_table_md(exercise: str, config: dict, rows: list) -> str:
    inputs = config["sample_inputs"]
    lines = [f"## {exercise}", ""]
    lines.append(f"Reference solution: `{config['reference_solution']}`")
    lines.append("")

    headers = ["submission_id"] + [f"input {i+1}: `{repr(inp)}`" for i, inp in enumerate(inputs)]
    lines.append("| " + " | ".join(headers) + " |")
    lines.append("|" + "---|" * len(headers))

    expected = [run_code(config["reference_solution"], inp) for inp in inputs]
    lines.append("| **expected** | " + " | ".join(f"**{e}**" for e in expected) + " |")

    for row in rows:
        if row["exercise"] != exercise:
            continue
        actuals = [run_code(row["code"], inp) for inp in inputs]
        lines.append("| " + row["submission_id"] + " | " + " | ".join(actuals) + " |")

    lines.append("")
    return "\n".join(lines)


def main():
    rows = build_rows()
    sections = [
        "# Wrong-answer sub-clustering: input/output reading aid",
        "",
        "Companion to `subcluster_ground_truth_sample.csv`/`.md` -- same 29 submissions, "
        "same ids. Each cell is the literal stdout each submission's code actually "
        "produced when run against that input (or `ERROR: <ExceptionType>`/`ERROR: "
        "Timeout` if it crashed or hung). Nothing here is interpreted or grouped -- "
        "compare a row against the **expected** row to spot mismatches, then fill in "
        "`bug_group` in the CSV yourself.",
        "",
    ]
    for exercise, config in EXERCISE_IO_CONFIG.items():
        sections.append(build_table_md(exercise, config, rows))

    OUT_PATH.write_text("\n".join(sections))
    print(f"Wrote {OUT_PATH}")


if __name__ == "__main__":
    main()
