"""
Bridges feedback-research/ (classify.py + feedback.py) into the live backend.

feedback-research/ is a plain research snapshot, not a Python package (its
directory name has a hyphen, and it deliberately mirrors classification-test's
files byte-for-byte rather than being restructured for import). Loaded by file
path via importlib instead of sys.path/package tricks.
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


def hint_for_submission(test_results: list, attempt_number: int, expected_function_name: str = None) -> dict:
    """Runs the research classify.py on the first failing test case and escalates
    the result via hint_for_attempt().

    Returns hint_text=None (with hint_tier/hint_ceiling=None) when nothing failed.
    Callers should wrap this in try/except: if the research taxonomy doesn't
    recognize a (verdict, error_type) pair (e.g. the two taxonomies drift apart
    later), ceiling_for()/hint_for_attempt() raise ValueError rather than
    returning a sentinel -- that should degrade to "no hint available", not 500
    the submission endpoint.
    """
    failing = next((r for r in test_results if not r["passed"]), None)
    if failing is None:
        return {
            "hint_text": None,
            "hint_tier": None,
            "hint_ceiling": None,
            "taxonomy_verdict": "pass",
            "taxonomy_error_type": None,
        }

    timed_out = "time limit" in (failing["status_description"] or "").lower()
    verdict, error_type = _classify.classify(
        stdout=failing["stdout"],
        stderr=failing["stderr"],
        exit_code=failing.get("exit_code"),
        expected_output=failing["expected_stdout"],
        timed_out=timed_out,
        expected_function_name=expected_function_name,
    )
    shipped_ceiling = min(_feedback.ceiling_for(verdict, error_type), _feedback.SHIPPED_TIER_CAP)
    return {
        "hint_text": _feedback.hint_for_attempt(verdict, error_type, attempt_number, ship=True),
        "hint_tier": min(attempt_number, shipped_ceiling),
        "hint_ceiling": shipped_ceiling,
        "taxonomy_verdict": verdict,
        "taxonomy_error_type": error_type,
    }
