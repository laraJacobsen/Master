"""Step 4 of the CodeNet classifier eval: score production's classifier
(backend.hints.classify_submission, i.e. feedback-research/classify.py) against
CodeNet's judge labels, per language.

Each result in results.jsonl (run_judge0.py) is classified exactly as production
classifies a graded submission, and compared with the verdict its CodeNet status
should map to (EXPECTED). Two numbers per (language, status):

  agree        -- share classified as expected, over every submission
  agree (repr) -- the same, over only the submissions whose failure actually
                  reproduced on the sample input. CodeNet ships just the sample I/O
                  from the problem statement, not the judges' hidden tests, so a
                  Wrong Answer / TLE / MLE submission that passes the sample isn't a
                  classifier mistake -- the input that broke it isn't available.
                  Accepted and Presentation Error always count as reproduced: their
                  output is right, so a failure on the sample is production's
                  comparison (or Judge0's environment) disagreeing, which is a finding.

Then the full status x verdict confusion matrix per language, and the most common
last stderr/compile line among runtime_error/Unknown and misread compile errors --
the raw material for a C/Java classifier.

Prints Markdown, so it can be redirected into a findings doc:
    python feedback-research/codenet-eval/score.py > /tmp/score.md
"""

import json
import re
import sys
from collections import Counter, defaultdict

from select_problems import HERE, LANGUAGES, STATUSES

sys.path.insert(0, str(HERE.parents[1]))
from backend import hints  # noqa: E402

# What production's verdict should be for each CodeNet status. Python has no compile
# step, so AIZU files Python syntax errors under Runtime Error -- syntax_error counts
# as agreement there. compile_error isn't a verdict classify.py can produce yet; it's
# listed so the gap shows up as disagreement rather than being left out.
EXPECTED = {
    "Accepted": {"pass"},
    "WA: Presentation Error": {"pass"},  # production strips and reads the last line
    "Wrong Answer": {"wrong_answer"},
    "Runtime Error": {"runtime_error", "syntax_error", "function_not_found"},
    "Compile Error": {"compile_error"},
    "Time Limit Exceeded": {"timeout"},
    "Memory Limit Exceeded": {"oom"},
}
LOW_N = 30


def reproduced(record: dict) -> bool:
    if record["codenet_status"] in ("Accepted", "WA: Presentation Error"):
        return True
    return not record["result"]["passed"]


def last_line(result: dict) -> str:
    text = (result["compile_output"] or result["stderr"] or result["message"] or "").strip()
    line = text.splitlines()[-1] if text else ""
    # Normalize away what differs between otherwise-identical errors.
    line = re.sub(r"\d+", "N", line)
    return re.sub(r"\s+", " ", line).strip()[:100]


def label(verdict, error_type):
    return f"{verdict}/{error_type}" if error_type else verdict


def main():
    records, skipped = [], Counter()
    with open(HERE / "results.jsonl", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("skipped"):
                skipped[(r["language"], r["codenet_status"], r["skipped"])] += 1
                continue
            r["verdict"], r["error_type"] = hints.classify_submission([r["result"]])
            records.append(r)

    by_cell = defaultdict(list)
    for r in records:
        by_cell[(r["language"], r["codenet_status"])].append(r)

    print(f"# CodeNet classifier eval\n\n{len(records)} submissions scored.")
    for (lang, status, reason), n in sorted(skipped.items()):
        print(f"{n} {lang} {status} skipped as {reason} (production rejects these before Judge0).")
    decode = sum(r["decode_errors"] for r in records)
    if decode:
        print(f"{decode} had source bytes that aren't valid UTF-8 (kept, replaced with U+FFFD).")

    print("\n## Agreement per language and status\n")
    print("| language | CodeNet status | n | agree | reproduced on sample | agree (reproduced) |")
    print("|---|---|---:|---:|---:|---:|")
    for lang in LANGUAGES:
        for status in STATUSES:
            cell = by_cell.get((lang, status), [])
            if not cell:
                continue
            agree = sum(r["verdict"] in EXPECTED[status] for r in cell)
            repr_ = [r for r in cell if reproduced(r)]
            agree_repr = sum(r["verdict"] in EXPECTED[status] for r in repr_)
            low = " (low n)" if len(cell) < LOW_N else ""
            pct = lambda a, b: f"{a / b:.0%}" if b else "-"
            print(f"| {lang} | {status}{low} | {len(cell)} | {pct(agree, len(cell))} "
                  f"| {pct(len(repr_), len(cell))} | {pct(agree_repr, len(repr_))} |")

    for lang in LANGUAGES:
        lang_records = [r for r in records if r["language"] == lang]
        if not lang_records:
            continue
        labels = [l for l, _ in Counter(label(r["verdict"], r["error_type"]) for r in lang_records).most_common()]
        print(f"\n## {lang}: CodeNet status x production verdict\n")
        print("| CodeNet status | " + " | ".join(labels) + " |")
        print("|---|" + "---:|" * len(labels))
        for status in STATUSES:
            cell = by_cell.get((lang, status), [])
            if not cell:
                continue
            counts = Counter(label(r["verdict"], r["error_type"]) for r in cell)
            print(f"| {status} | " + " | ".join(str(counts[l] or "") for l in labels) + " |")

    print("\n## What the classifier doesn't recognize yet\n")
    print("Most common last stderr/compile line (digits -> N) where production said "
          "runtime_error/Unknown, or where Judge0 reported a compilation error.\n")
    for lang in LANGUAGES:
        unknown = Counter(
            last_line(r["result"]) for r in records
            if r["language"] == lang and (
                (r["verdict"], r["error_type"]) == ("runtime_error", "Unknown")
                or r["result"]["status_description"] == "Compilation Error")
        )
        if not unknown:
            continue
        print(f"\n**{lang}** ({sum(unknown.values())})\n")
        for line, n in unknown.most_common(12):
            print(f"- {n} x `{line}`")

    exit_codes = Counter(r["result"]["exit_code"] for r in records)
    print(f"\n## Judge0 exit_code values\n\n{dict(exit_codes)}")


if __name__ == "__main__":
    main()
