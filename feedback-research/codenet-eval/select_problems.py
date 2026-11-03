"""Step 1 of the CodeNet classifier eval: pick which CodeNet problems to sample
submissions from.

A problem qualifies when it has a sample I/O pair (derived/input_output/data/<id>/
input.txt + output.txt -- CodeNet ships only the sample from the problem statement,
not the judges' hidden tests) and real submissions in C, Java and Python 3. It is
then ranked by how many of the (language x status) cells we want to score have at
least --min-per-cell submissions, so the sample can be stratified without empty
cells. Ties go to the problem with the shortest median accepted Python solution:
CodeNet has no difficulty field for AIZU problems, and a short typical solution is
the closest available proxy for "lecture-sized".

Python 2 is excluded (classify.py reads Python 3 tracebacks, and Judge0 runs 3.8);
the Python major version is read from original_language, e.g. "Python (3.4.2)",
"Python3", "PyPy3 (2.4.0)" -> 3, "Python (2.7.6)", "PyPy2 (5.6.0)" -> 2. Anything
that doesn't parse is excluded and listed in the summary, so nothing is guessed --
in practice that's AIZU's bare "Python", which (as far as we know) was 2.7.

Writes problems.csv (the selected ids plus their per-cell counts -- metadata only,
no CodeNet code) next to this script, and prints a summary of the original_language
and status values seen, to check the filters against.

Usage:
    python feedback-research/codenet-eval/select_problems.py
    python feedback-research/codenet-eval/select_problems.py --dataset AIZU --top 10
    python feedback-research/codenet-eval/select_problems.py --dataset AIZU --max-median-size 300

CODENET_DIR overrides where Project_CodeNet/ was extracted
(default ~/datasets/codenet/Project_CodeNet).
"""

import argparse
import csv
import os
import re
import statistics
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
CODENET_DIR = Path(os.environ.get("CODENET_DIR", Path.home() / "datasets" / "codenet" / "Project_CodeNet"))

LANGUAGES = ["C", "Java", "Python"]
STATUSES = [
    "Accepted", "Wrong Answer", "Runtime Error", "Compile Error",
    "Time Limit Exceeded", "Memory Limit Exceeded",
    # Right answer, wrong whitespace/formatting. production's comparison strips and
    # reads only the last printed line, so these should grade as pass -- scoring them
    # measures how lenient that comparison really is.
    "WA: Presentation Error",
]

_PY_MAJOR_RE = re.compile(r"(?:python|pypy)\s*\(?\s*(\d)", re.IGNORECASE)


def python_major(original_language: str):
    m = _PY_MAJOR_RE.search(original_language)
    return int(m.group(1)) if m else None


def has_sample_io(problem_id: str) -> bool:
    io_dir = CODENET_DIR / "derived" / "input_output" / "data" / problem_id
    # input.txt may legitimately be empty (a problem that reads nothing);
    # an empty expected output can't tell pass from wrong_answer, so it's out.
    return (io_dir / "input.txt").is_file() and (io_dir / "output.txt").is_file() \
        and (io_dir / "output.txt").stat().st_size > 0


def scan_problem(problem_id: str, original_languages: Counter, statuses: Counter, unparsed: Counter):
    """Per-(language, status) submission counts for one problem, plus the
    code_size of its accepted Python 3 submissions."""
    cells = Counter()
    py_ac_sizes = []
    with open(CODENET_DIR / "metadata" / f"{problem_id}.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            lang = row["language"]
            if lang not in LANGUAGES:
                continue
            original_languages[(lang, row["original_language"])] += 1
            statuses[row["status"]] += 1
            if lang == "Python":
                major = python_major(row["original_language"])
                if major is None:
                    unparsed[row["original_language"]] += 1
                    continue
                if major != 3:
                    continue
                if row["status"] == "Accepted" and row["code_size"].isdigit():
                    py_ac_sizes.append(int(row["code_size"]))
            if row["status"] in STATUSES:
                cells[(lang, row["status"])] += 1
    return cells, py_ac_sizes


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", choices=["AIZU", "AtCoder"], help="only problems from this judge")
    parser.add_argument("--top", type=int, default=10, help="how many problems to select")
    parser.add_argument("--min-per-cell", type=int, default=20,
                        help="submissions a (language, status) cell needs to count as covered")
    parser.add_argument("--max-median-size", type=int,
                        help="drop problems whose median accepted Python 3 solution is longer "
                             "than this many bytes (a proxy for lecture-sized)")
    args = parser.parse_args()

    if not (CODENET_DIR / "metadata" / "problem_list.csv").is_file():
        raise SystemExit(f"No CodeNet metadata under {CODENET_DIR} -- set CODENET_DIR.")

    with open(CODENET_DIR / "metadata" / "problem_list.csv", newline="", encoding="utf-8") as f:
        problems = [p for p in csv.DictReader(f) if not args.dataset or p["dataset"] == args.dataset]
    problems = [p for p in problems if has_sample_io(p["id"])
                and (CODENET_DIR / "metadata" / f"{p['id']}.csv").is_file()]
    print(f"{len(problems)} problems with sample I/O and metadata; scanning submissions...")

    original_languages, statuses, unparsed = Counter(), Counter(), Counter()
    ranked = []
    for i, p in enumerate(problems, 1):
        if i % 250 == 0:
            print(f"  {i}/{len(problems)}")
        cells, py_ac_sizes = scan_problem(p["id"], original_languages, statuses, unparsed)
        # Every language needs accepted solutions: they're the pass baseline,
        # and a problem nobody solved in C/Java is no use for comparing languages.
        if any(cells[(lang, "Accepted")] < args.min_per_cell for lang in LANGUAGES) or not py_ac_sizes:
            continue
        median_size = statistics.median(py_ac_sizes)
        if args.max_median_size and median_size > args.max_median_size:
            continue
        covered = sum(1 for lang in LANGUAGES for s in STATUSES if cells[(lang, s)] >= args.min_per_cell)
        ranked.append((covered, median_size, p, cells))

    ranked.sort(key=lambda r: (-r[0], r[1]))
    selected = ranked[: args.top]

    cell_names = [f"{lang}:{s}" for lang in LANGUAGES for s in STATUSES]
    out_path = HERE / "problems.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name", "dataset", "time_limit", "memory_limit",
                         "cells_covered", "median_py_ac_code_size"] + cell_names)
        for covered, median_size, p, cells in selected:
            writer.writerow([p["id"], p["name"], p["dataset"], p["time_limit"], p["memory_limit"],
                             covered, int(median_size)]
                            + [cells[(lang, s)] for lang in LANGUAGES for s in STATUSES])

    print(f"\n{len(ranked)} problems qualified; wrote the top {len(selected)} to {out_path}")
    print(f"(cells covered out of {len(LANGUAGES) * len(STATUSES)}, median accepted Python 3 code size)")
    for covered, median_size, p, _ in selected:
        print(f"  {p['id']}  {covered:2d}  {int(median_size):5d}B  {p['name']}")

    print("\noriginal_language values (top 10 per language):")
    for lang in LANGUAGES:
        top = [(o, n) for (l, o), n in original_languages.most_common() if l == lang][:10]
        print(f"  {lang}: " + ", ".join(f"{o} ({n})" for o, n in top))
    print("\nstatus values:")
    for s, n in statuses.most_common():
        print(f"  {s}: {n}{'' if s in STATUSES else '   <- not scored'}")
    if unparsed:
        print("\nPython original_language values with no parseable version (excluded):")
        for o, n in unparsed.most_common():
            print(f"  {o}: {n}")


if __name__ == "__main__":
    main()
