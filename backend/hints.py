"""
Bridges feedback-research/ (classify.py + feedback.py) into the live backend.

feedback-research/ is a plain research snapshot, not a Python package (its
directory name has a hyphen, and it deliberately mirrors classification-test's
files byte-for-byte rather than being restructured for import). Loaded by file
path via importlib instead of sys.path/package tricks.

This is now the ONLY deterministic Judge0-result classifier in the backend --
it replaced the old backend/exec_verdict.py, which duplicated this same job
with a coarser taxonomy (no exception-name detail) purely because it predated
this module and nobody merged them. classify_submission() feeds both the
`exec_verdict` column (lecturer aggregation) and hint_for_verdict() (student
hint text) from one classification, instead of classifying the same
test_results twice with two different fixed taxonomies.
"""

import importlib.util
import os

_RESEARCH_DIR = os.path.join(os.path.dirname(__file__), "..", "feedback-research")


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, os.path.join(_RESEARCH_DIR, filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_classify = _load("_research_classify", "classify.py")
_feedback = _load("_research_feedback", "feedback.py")


def classify_submission(test_results: list, expected_function_name: str = None) -> tuple:
    """Single source of truth for a submission's deterministic (verdict, error_type),
    from the research classify.py run against the first failing test case.

    Returns ("pass", None) when every test case passed. error_type is only set
    when verdict == "runtime_error" (it's the exception name, e.g. "NameError").
    """
    failing = next((r for r in test_results if not r["passed"]), None)
    if failing is None:
        return "pass", None

    timed_out = "time limit" in (failing["status_description"] or "").lower()
    return _classify.classify(
        stdout=failing["stdout"],
        stderr=failing["stderr"],
        exit_code=failing.get("exit_code"),
        expected_output=failing["expected_stdout"],
        timed_out=timed_out,
        expected_function_name=expected_function_name,
    )


def hint_for_verdict(verdict: str, error_type: str, attempt_number: int) -> dict:
    """Escalates an already-classified (verdict, error_type) into hint text via
    feedback.py's hint_for_attempt(). Returns hint_text=None (hint_tier/
    hint_ceiling=None) for verdict == "pass" -- nothing to hint about.

    Callers should wrap this in try/except: if the taxonomy doesn't recognize
    the (verdict, error_type) pair (e.g. classify.py starts returning a verdict
    feedback.py has no family for), ceiling_for()/hint_for_attempt() raise
    ValueError rather than returning a sentinel -- that should degrade to "no
    hint available", not 500 the submission endpoint.
    """
    if verdict == "pass":
        return {"hint_text": None, "hint_tier": None, "hint_ceiling": None}

    shipped_ceiling = min(_feedback.ceiling_for(verdict, error_type), _feedback.SHIPPED_TIER_CAP)
    return {
        "hint_text": _feedback.hint_for_attempt(verdict, error_type, attempt_number, ship=True),
        "hint_tier": min(attempt_number, shipped_ceiling),
        "hint_ceiling": shipped_ceiling,
    }


def discussion_point_for_cluster(verdict: str, error_type: str, student_count: int) -> str:
    """Deterministic lecturer talking-point text for a cluster of students who hit the
    same (verdict, error_type) issue -- see feedback.py's discussion_point_for().

    Callers should wrap this in try/except, same as hint_for_verdict(): an
    unrecognized (verdict, error_type) pair should degrade to "no discussion point",
    not crash the lecturer aggregation endpoint.
    """
    return _feedback.discussion_point_for(verdict, error_type, student_count)


def mechanism_for_cluster(verdict: str, error_type: str) -> str:
    """Just the curated 'what this category means' sentence, no framing or count --
    see feedback.py's mechanism_for(). Used to keep that factual content in the
    discussion point even when a model-written lead-in is composed in front of it
    (backend/aggregation.py) -- the lead-in must never replace it.
    """
    return _feedback.mechanism_for(verdict, error_type)
