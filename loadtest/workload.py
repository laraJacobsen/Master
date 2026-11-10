"""What the simulated class submits: the question, the corpus mix, and one
plan per student for each scenario.

The code comes from feedback-research/corpora/corpus.py (25 is_palindrome
submissions). That corpus defines its expected verdicts against one input
("Race car"), but the load-test question has more tests, so the verdict each
entry should get here is measured once, unloaded, by `run.py --scenario
calibrate` and saved to calibration.json. Under load, any submission whose
verdict differs from that is counted as wrong (e.g. a CPU-starved run killed by
the wall-time limit).
"""

import importlib.util
import json
import random
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CORPUS_PATH = REPO / "feedback-research" / "corpora" / "corpus.py"
CALIBRATION_PATH = Path(__file__).resolve().parent / "calibration.json"


def load_corpus() -> dict:
    spec = importlib.util.spec_from_file_location("lt_corpus", CORPUS_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return {c["id"]: c for c in mod.CASES}


CORPUS = load_corpus()
REFERENCE = CORPUS["01_correct_clean"]["code"]

# The first test is the worked example students see and is not graded (see
# main.py's _graded); the other two decide the verdict. Three Judge0 calls per
# submission, the same count as load_test.py's question.
PALINDROME_QUESTION = {
    "title": "Palindrome check",
    "prompt": (
        "Write a function is_palindrome(s) that returns True if s reads the same forwards "
        "and backwards, ignoring case and spaces, and False otherwise. Read one line from "
        "stdin, call is_palindrome on it, and print the result."
    ),
    "language": "python",
    "test_cases": [
        {"stdin": "Race car\n", "expected_stdout": "True"},
        {"stdin": "Never odd or even\n", "expected_stdout": "True"},
        {"stdin": "hello\n", "expected_stdout": "False"},
    ],
    "reference_solution": REFERENCE,
}

# Corpus entries by the category the mix draws from.
CATEGORIES = {
    "correct": ["01_correct_clean", "23_unicode_content"],
    # 02's debug prints go to stdout, so the backend's exact output match grades
    # it incorrect (0/2) even though the corpus calls it "pass" -- see calibration.json.
    "wrong_answer": [
        "02_correct_with_debug_prints", "03_wrong_case_sensitive", "04_wrong_unstripped_spaces",
        "05_wrong_off_by_one",
    ],
    "syntax": ["06_syntax_error", "07_indentation_error"],
    "runtime": [
        "08_name_error", "09_type_error_str_int", "10_index_error", "11_attribute_error",
        "12_recursion_error", "13_wrong_signature", "14_function_not_found",
        "17_blocking_input_eof", "24_disallowed_import", "25_key_error",
    ],
    "timeout": ["15_timeout_missing_increment"],
    "other": [
        "16_output_flood", "18_oom_direct_allocation", "19_oom_growing_loop",
        "20_empty_submission", "21_whitespace_only", "22_oversized_submission",
    ],
}
# Mostly correct / wrong answer, some syntax and runtime errors, a few timeouts.
MIX = {"correct": 40, "wrong_answer": 30, "syntax": 10, "runtime": 15, "timeout": 3, "other": 2}

# load_test.py's question and plans, for the --scenario legacy reproduction.
LEGACY_CORRECT = "nums = input().split()\nprint(sum(int(n) for n in nums))"
LEGACY_WRONG = "nums = input().split()\nprint(sum(int(n) for n in nums) + 1)"
LEGACY_CRASH = "nums = inpt().split()\nprint(sum(int(n) for n in nums))"
LEGACY_QUESTION = {
    "title": "Sum the numbers",
    "prompt": "Read space-separated integers and print their sum.",
    "language": "python",
    "test_cases": [
        {"stdin": "1 2 3\n", "expected_stdout": "6"},
        {"stdin": "10\n", "expected_stdout": "10"},
        {"stdin": "-4 4 7\n", "expected_stdout": "7"},
    ],
    "reference_solution": LEGACY_CORRECT,
}
LEGACY_ENTRIES = {
    "legacy_correct": {"code": LEGACY_CORRECT, "expected": "correct"},
    "legacy_wrong": {"code": LEGACY_WRONG, "expected": "incorrect"},
    "legacy_crash": {"code": LEGACY_CRASH, "expected": "error"},
}
LEGACY_PLANS = [  # (weight, [entry ids]) -- same as load_test.py's PLANS
    (5, ["legacy_correct"]),
    (3, ["legacy_wrong", "legacy_correct"]),
    (2, ["legacy_crash", "legacy_correct"]),
]


@dataclass
class Step:
    entry_id: str
    category: str
    at: float | None = None  # seconds after task start; None = after the previous verdict
    think_s: float = 0.0  # used when at is None
    only_if_failed: bool = False  # skip once the student has a correct verdict


@dataclass
class StudentPlan:
    name: str
    steps: list = field(default_factory=list)


def code_for(entry_id: str) -> str:
    if entry_id in LEGACY_ENTRIES:
        return LEGACY_ENTRIES[entry_id]["code"]
    return CORPUS[entry_id]["code"]


def load_calibration() -> dict:
    """entry id -> {"verdict", "tests_passed"} from the last calibrate run, or {}."""
    if CALIBRATION_PATH.exists():
        return json.loads(CALIBRATION_PATH.read_text())["expected"]
    return {}


def expected_for(entry_id: str, calibration: dict):
    if entry_id in LEGACY_ENTRIES:
        return {"verdict": LEGACY_ENTRIES[entry_id]["expected"], "tests_passed": None}
    return calibration.get(entry_id)


def _draw(rng: random.Random, category: str = None):
    if category is None:
        category = rng.choices(list(MIX), weights=list(MIX.values()))[0]
    return rng.choice(CATEGORIES[category]), category


def names(n: int) -> list:
    return [f"LT-Student{i:03d}" for i in range(1, n + 1)]


def plans_single() -> list:
    """One student, one correct submit at t=12 s -- late enough that status polls
    and a heartbeat have happened first, so the whole flow is exercised."""
    return [StudentPlan("LT-Student001", [Step("01_correct_clean", "correct", at=12.0)])]


def plans_calibrate() -> list:
    """One student, every corpus entry once, one after another (never two in flight)."""
    steps = [Step(eid, next(c for c, ids in CATEGORIES.items() if eid in ids), at=None, think_s=0.5)
             for eid in CORPUS]
    steps[0].at = 1.0
    return [StudentPlan("LT-Calibrator", steps)]


def plans_steady(n: int, window: float, rng: random.Random) -> list:
    """First submissions uniform over the task window; no resubmits."""
    out = []
    for name in names(n):
        eid, cat = _draw(rng)
        out.append(StudentPlan(name, [Step(eid, cat, at=rng.uniform(0, window))]))
    return out


def plans_burst(n: int, window: float, rng: random.Random, burst_share=0.8, burst_spread=10.0) -> list:
    """burst_share of the class submits in [time-up, time-up + burst_spread] -- the
    auto-submit at time-up plus last-second clicks; the rest spread over the window."""
    out = []
    for name in names(n):
        eid, cat = _draw(rng)
        if rng.random() < burst_share:
            at = window + rng.uniform(0, burst_spread)
        else:
            at = rng.uniform(0, window)
        out.append(StudentPlan(name, [Step(eid, cat, at=at)]))
    return out


def plans_resubmit(n: int, window: float, rng: random.Random) -> list:
    """First submissions spread over the first half of the window; a student whose
    verdict isn't correct resubmits after 15-45 s -- once with a fix (60%), or once
    more wrong then fixed (40%). Resubmits that would land after time-up are
    dropped by run.py (the student page stops accepting them)."""
    out = []
    for plan in plans_steady(n, window / 2, rng):  # first half, leaving time to resubmit
        if rng.random() < 0.6:
            follow = [_draw(rng, "correct")]
        else:
            follow = [_draw(rng, rng.choice(["wrong_answer", "runtime", "syntax"])), _draw(rng, "correct")]
        for eid, cat in follow:
            plan.steps.append(Step(eid, cat, at=None, think_s=rng.uniform(15, 45), only_if_failed=True))
        out.append(plan)
    return out


def plans_legacy(n: int, rng: random.Random) -> list:
    """load_test.py --mode burst: first submit within 1 s, fixed follow-ups 3-8 s later."""
    out = []
    weights = [w for w, _ in LEGACY_PLANS]
    for name in names(n):
        _, entries = rng.choices(LEGACY_PLANS, weights)[0]
        steps = [Step(entries[0], entries[0], at=rng.uniform(0, 1))]
        steps += [Step(e, e, at=None, think_s=rng.uniform(3, 8)) for e in entries[1:]]
        out.append(StudentPlan(name, steps))
    return out
