"""
Grading module. Fully deterministic -- no model in the loop.

An LLM (local Ollama, llama3.2:3b) originally judged verdict/error_type and wrote a
lecturer discussion point per submission. Both jobs are gone now:

- verdict/error_type never actually needed a model: verdict is a plain threshold on
  test pass/fail counts (_coarse_verdict), and error_type is hints.classify_submission()
  reading stdout/stderr directly -- the same classifier that already drives the
  student-facing hint text.
- discussion_point (the lecturer talking point) was asked of Ollama per submission and
  proved unreliable even when handed the exact correct classification -- it fabricated
  causes that didn't match the actual bug (e.g. blaming a missing import on a plain typo
  in a call to input()). It's also not a per-submission thing: the same LLM call ran
  again on every resubmission of identical code, producing inconsistent text for one
  student's one mistake instead of one stable talking point for the class. It's now
  generated deterministically, once per cluster of students who hit the same issue --
  see aggregation.py and feedback-research/feedback.py's discussion_point_for().

See feedback-research/pedagogical-feedback-design-decision.md for the history (the
latency/memory cost of running Ollama locally was the other reason it was cut, on top
of the reliability problem above).
"""

from backend.hints import classify_submission, hint_for_verdict

VERDICTS = ("correct", "partially_correct", "incorrect", "error")


def _coarse_verdict(exec_verdict: str, passed: int, total: int) -> str:
    """Deterministic verdict bucket for the frontend badges (correct/partially_correct/
    incorrect/error), derived from the same exec_verdict classify_submission() already
    computed -- a plain threshold on pass/fail counts, no model needed."""
    if total > 0 and passed == total:
        return "correct"
    if passed > 0:
        return "partially_correct"
    return "incorrect" if exec_verdict in ("wrong_answer", "pass") else "error"


def judge_and_feedback(
    question_prompt: str,
    source_code: str,
    test_results: list,
    language: str = "python",
    attempt_number: int = 1,
    expected_function_name: str = None,
) -> dict:
    """Returns a dict: verdict, error_type, feedback, tests_passed, tests_total,
    hint_tier, hint_ceiling, exec_verdict.

    question_prompt/source_code/language are unused now that grading has no model to
    give them to -- kept as parameters so main.py's call site doesn't need to change
    based on which grading strategy is in use.
    """
    passed = sum(1 for r in test_results if r["passed"])
    total = len(test_results)
    baseline_feedback = (
        f"All {total} test cases passed!"
        if total and passed == total
        else f"{passed}/{total} test cases passed. Review the cases that didn't match."
    )

    try:
        exec_verdict, error_type = classify_submission(test_results, expected_function_name)
        hint = hint_for_verdict(exec_verdict, error_type, attempt_number)
    except Exception:
        exec_verdict = "pass" if passed == total and total > 0 else "wrong_answer"
        error_type = None
        hint = {"hint_text": None, "hint_tier": None, "hint_ceiling": None}

    result = {
        "verdict": _coarse_verdict(exec_verdict, passed, total),
        "error_type": error_type,
        "feedback": baseline_feedback,
        "tests_passed": passed,
        "tests_total": total,
    }

    if hint["hint_text"] is not None:
        result["feedback"] = hint["hint_text"]
    result["hint_tier"] = hint["hint_tier"]
    result["hint_ceiling"] = hint["hint_ceiling"]
    result["exec_verdict"] = exec_verdict
    return result
