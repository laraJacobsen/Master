"""Step 3 of the CodeNet classifier eval: run every submission in sample.csv on its
problem's sample input through Judge0, exactly as production grades a submission.

Calls backend.judge0_client.run_test_cases() with the problem's one sample I/O pair
as the only test case, so `passed` is production's own comparison (Accepted status +
stripped stdout equal) and each stored result is the same per-case dict that
hints.classify_submission() reads in production. CPU time and memory limits are the
problem's own AIZU limits from problems.csv, so Judge0 enforces what AIZU's judge did
(capped by judge0_client's MAX_* ceilings, as in production) -- except Java, which
gets JAVA_EXTRA_CPU_S more CPU and JAVA_MEMORY_LIMIT_KB memory. On this Judge0, JVM
startup alone measured 1.2-2.1s of CPU time (counted across all JVM threads, since
per-process time limits are off) and up to ~140MB, so at AIZU's 1s/128MB every Java
submission, accepted ones included, came back Time Limit Exceeded.

Results are appended to results.jsonl (gitignored), one line per submission, flushed
as each finishes -- rerunning skips submissions already in it, so an interrupted run
just picks up where it stopped. A Judge0 connectivity failure is not written (the
submission is retried on the next run); five in a row stops the run, since that means
Judge0 is down rather than one bad request.

Source files are decoded as UTF-8 with replacement; old AIZU submissions in another
encoding (e.g. Shift-JIS comments) are flagged with decode_errors=True rather than
dropped, so score.py can exclude them if they turn out to matter.

Usage (Judge0 running; JUDGE0_BASE_URL as for the backend):
    python feedback-research/codenet-eval/run_judge0.py
    python feedback-research/codenet-eval/run_judge0.py --workers 4 --limit 50
"""

import argparse
import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from select_problems import CODENET_DIR, HERE
from sample_submissions import source_path

sys.path.insert(0, str(HERE.parents[1]))
from backend import judge0_client  # noqa: E402

RESULTS_PATH = HERE / "results.jsonl"
JUDGE0_LANGUAGE = {"C": "c", "Java": "java", "Python": "python"}
JAVA_EXTRA_CPU_S = 3
JAVA_MEMORY_LIMIT_KB = 256000  # = judge0_client's default MAX_MEMORY_LIMIT_KB
MAX_CONSECUTIVE_JUDGE0_ERRORS = 5


def load_done() -> set:
    if not RESULTS_PATH.is_file():
        return set()
    with open(RESULTS_PATH, encoding="utf-8") as f:
        return {json.loads(line)["submission_id"] for line in f if line.strip()}


def sample_io(problem_id: str) -> dict:
    io_dir = CODENET_DIR / "derived" / "input_output" / "data" / problem_id
    return {
        "stdin": (io_dir / "input.txt").read_text(encoding="utf-8"),
        "expected_stdout": (io_dir / "output.txt").read_text(encoding="utf-8"),
    }


def run_one(row: dict, problem: dict, test_case: dict) -> dict:
    raw = source_path(row).read_bytes()
    source = raw.decode("utf-8", errors="replace")
    record = {
        "submission_id": row["submission_id"],
        "problem_id": row["problem_id"],
        "language": row["language"],
        "codenet_status": row["status"],
        "decode_errors": "�" in source and b"\xef\xbf\xbd" not in raw,
    }
    if not source.strip():
        # Judge0 refuses blank source (422). Production never sends it either --
        # validation.pre_execution_check() rejects it first -- so it's recorded
        # as skipped, and score.py reports it instead of scoring it.
        return {**record, "skipped": "whitespace_only", "result": None}
    cpu_time_limit = int(problem["time_limit"]) / 1000
    memory_limit_kb = int(problem["memory_limit"])
    if row["language"] == "Java":
        cpu_time_limit += JAVA_EXTRA_CPU_S
        memory_limit_kb = max(memory_limit_kb, JAVA_MEMORY_LIMIT_KB)
    result = judge0_client.run_test_cases(
        source,
        [test_case],
        language=JUDGE0_LANGUAGE[row["language"]],
        cpu_time_limit=cpu_time_limit,
        memory_limit_kb=memory_limit_kb,
    )[0]
    return {**record, "result": result}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--workers", type=int, default=4,
                        help="parallel Judge0 calls (match Judge0's worker count)")
    parser.add_argument("--limit", type=int,
                        help="only run this many, spread across the sample (for a trial run)")
    args = parser.parse_args()

    with open(HERE / "problems.csv", newline="", encoding="utf-8") as f:
        problems = {p["id"]: p for p in csv.DictReader(f)}
    test_cases = {pid: sample_io(pid) for pid in problems}
    with open(HERE / "sample.csv", newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    done = load_done()
    todo = [r for r in rows if r["submission_id"] not in done]
    if args.limit:
        # Evenly spaced through the sample (which is ordered by problem, language,
        # status), so a trial run touches every language and status, not just the
        # first cell.
        todo = todo[:: max(1, len(todo) // args.limit)][: args.limit]
    print(f"{len(rows)} in sample, {len(done)} already done, running {len(todo)} "
          f"against {judge0_client.JUDGE0_BASE_URL} with {args.workers} workers")

    consecutive_errors = 0
    finished = 0
    started = time.monotonic()
    with open(RESULTS_PATH, "a", encoding="utf-8") as out, ThreadPoolExecutor(args.workers) as pool:
        futures = {pool.submit(run_one, r, problems[r["problem_id"]], test_cases[r["problem_id"]]): r
                   for r in todo}
        for future in as_completed(futures):
            row = futures[future]
            try:
                record = future.result()
            except judge0_client.Judge0Error as e:
                consecutive_errors += 1
                print(f"  Judge0 error on {row['submission_id']}: {e}")
                if consecutive_errors >= MAX_CONSECUTIVE_JUDGE0_ERRORS:
                    print("Judge0 looks down -- stopping. Rerun to resume.")
                    for f in futures:
                        f.cancel()
                    break
                continue
            consecutive_errors = 0
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            out.flush()
            finished += 1
            if finished % 100 == 0:
                rate = finished / (time.monotonic() - started)
                print(f"  {finished}/{len(todo)}  ({rate:.1f}/s, ~{(len(todo) - finished) / rate / 60:.0f} min left)")

    print(f"Done: {finished} written to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
