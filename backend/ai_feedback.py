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

See feedback-research/decisions/pedagogical-feedback-design-decision.md for the history (the
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


_TRACEBACK_MAX_CHARS = 2000


def _traceback_for(test_results: list) -> str:
    """Raw stderr from the first failing test case -- or, for a program that
    didn't compile, the compiler's output -- or None if it passed or produced
    neither (e.g. a plain wrong-answer). Several hint tiers (see
    feedback-research/feedback.py) explicitly tell the student to "read the
    traceback" or the compiler's first error -- that only makes sense if the
    student can actually see it."""
    failing = next((r for r in test_results if not r["passed"]), None)
    if failing is None:
        return None
    stderr = failing.get("stderr") or failing.get("compile_output")
    if not stderr:
        return None
    if len(stderr) > _TRACEBACK_MAX_CHARS:
        stderr = stderr[:_TRACEBACK_MAX_CHARS] + "\n... (truncated)"
    return stderr


_QUOTE_MAX_CHARS = 60

# Last generic wrong-answer hint when the example passes but a hidden test doesn't.
EXAMPLE_PASSES_HINT = (
    "Your program gets the example right, so the bug only shows up on a test the example "
    "doesn't cover. Try it on small edge cases: a single value, zero or negative numbers, "
    "repeated values, or the biggest value first or last. Which one gives the wrong output?"
)


def _quote(line: str) -> str:
    line = line.strip()
    if len(line) > _QUOTE_MAX_CHARS:
        line = line[:_QUOTE_MAX_CHARS] + "..."
    return f'"{line}"'


def _example_diff_hint(example: dict, output_file: str = None) -> str:
    """The last generic wrong-answer hint, made concrete from the example test (the
    one test students can see). feedback.py's own last tier can only say "find where
    it diverges", since it never sees a test; this says exactly where. Returns None
    when the example didn't run cleanly (a crash has its own hints)."""
    if example.get("status_description") != "Accepted":
        return None
    if example["passed"]:
        return EXAMPLE_PASSES_HINT
    # Same normalization as judge0_client.outputs_match(), so the line found here is
    # the one that actually failed the comparison.
    norm = lambda t: [ln.rstrip() for ln in (t or "").strip().splitlines()]
    got, expected = norm(example.get("stdout")), norm(example["expected_stdout"])
    yours = f"your {output_file}" if output_file else "your output"
    if not got:
        return (f"On the example input, {yours} is empty, but it should start with "
                f"{_quote(expected[0])}. Check that your program actually writes its result.")
    i = next((k for k in range(min(len(got), len(expected))) if got[k] != expected[k]), None)
    if i is None and len(got) < len(expected):
        return (f"On the example input, {yours} stops after line {len(got)}. Line "
                f"{len(got) + 1} should be {_quote(expected[len(got)])}. What step is missing?")
    if i is None:
        return (f"On the example input, {yours} has an extra line {len(expected) + 1}: "
                f"{_quote(got[len(expected)])}. The expected output ends before it. "
                f"Where does that line come from?")
    where = "" if len(expected) == 1 and len(got) == 1 else f"line {i + 1} of "
    return (f"On the example input, {where}{yours} is {_quote(got[i])}, but it should be "
            f"{_quote(expected[i])}. Find the step in your code that produces that value and "
            f"fix it.")


def _tests_wrong_answer_hints(test_results: list) -> list:
    """Generic wrong-answer hints for a test-graded task (no lecturer ladder), attempt 1
    first. feedback.py's wrong_answer tiers talk about printed output and the example
    input, which a pytest task doesn't have. These point at the first failing visible
    test -- whose name and message the student already sees -- and only ever count
    hidden tests, never name them."""
    failing = [r for r in test_results if not r["passed"]]
    visible = [r for r in failing if r.get("visibility") != "hidden"]
    hidden = len(failing) - len(visible)
    if visible:
        first = visible[0]
        where = f"{first.get('test_file')}" if first.get("test_file") else "the tests folder"
        return [
            f"Your code runs, but {len(failing)} test{'s' if len(failing) != 1 else ''} fail. Start with "
            f"{first.get('test_name')}: its message shows what it checked and what your code gave.",
            f"Open {where} and find {first.get('test_name')}. Call your function yourself with the same "
            f"input it uses and print the result. Where does it differ from what the test expects?",
            f"{first.get('test_name')} fails with: {_quote(first.get('message') or '')}. Find the line in your "
            f"code that produces that value and fix it.",
        ]
    return [
        f"Every visible test passes, but {hidden} hidden test{'s' if hidden != 1 else ''} "
        f"fail{'' if hidden != 1 else 's'}. The hidden tests check cases the visible ones don't cover.",
        TESTS_HIDDEN_HINT,
        TESTS_HIDDEN_HINT,
    ]


# Last generic wrong-answer hint of a test-graded task when only hidden tests fail.
TESTS_HIDDEN_HINT = (
    "Re-read the task description for every case it mentions, then try your code on input the "
    "visible tests don't use: missing or empty values, a single row or none, ties, or different "
    "data than the example file. Which one gives a wrong result?"
)


def judge_and_feedback(
    question_prompt: str,
    source_code: str,
    test_results: list,
    language: str = "python",
    attempt_number: int = 1,
    expected_function_name: str = None,
    hint_ladder: list = None,
    example_result: dict = None,
    output_file: str = None,
    grading_mode: str = "stdout",
) -> dict:
    """Returns a dict: verdict, error_type, feedback, tests_passed, tests_total,
    hint_tier, hint_ceiling, exec_verdict, traceback.

    language picks the crash rules classify_submission() applies. question_prompt/
    source_code are unused now that grading has no model to give them to -- kept as
    parameters so main.py's call site doesn't need to change based on which grading
    strategy is in use.

    hint_ladder is the task's own lecturer-approved wrong-answer hints (see
    backend/hint_ladder.py). When set, a wrong answer gets those, escalating by
    attempt, instead of feedback.py's generic ones. Crashes, syntax errors and
    timeouts keep feedback.py's error-specific hints.

    example_result is the example test's result (the test students can see). Without
    a ladder, a wrong answer's last hint quotes where the output differs from it
    (see _example_diff_hint()) instead of feedback.py's generic last tier.

    grading_mode "tests": test_results are task_runner TestResult dicts (every test
    counts, visible and hidden). A wrong answer without a ladder gets
    _tests_wrong_answer_hints() instead of feedback.py's output-based ones; crashes keep
    feedback.py's error-specific hints, as in stdout mode.
    """
    passed = sum(1 for r in test_results if r["passed"])
    total = len(test_results)
    noun = "tests" if grading_mode == "tests" else "test cases"
    baseline_feedback = (
        f"All {total} {noun} passed!"
        if total and passed == total
        else f"{passed}/{total} {noun} passed. Review the cases that didn't match."
    )

    try:
        exec_verdict, error_type = classify_submission(test_results, expected_function_name, language)
        hint = hint_for_verdict(exec_verdict, error_type, attempt_number)
    except Exception:
        exec_verdict = "pass" if passed == total and total > 0 else "wrong_answer"
        error_type = None
        hint = {"hint_text": None, "hint_tier": None, "hint_ceiling": None}

    if exec_verdict == "wrong_answer" and hint_ladder:
        tier = min(attempt_number, len(hint_ladder))
        hint = {"hint_text": hint_ladder[tier - 1], "hint_tier": tier, "hint_ceiling": len(hint_ladder)}
    elif exec_verdict == "wrong_answer" and grading_mode == "tests":
        ladder = _tests_wrong_answer_hints(test_results)
        tier = min(max(attempt_number, 1), len(ladder))
        hint = {"hint_text": ladder[tier - 1], "hint_tier": tier, "hint_ceiling": len(ladder)}
    elif (exec_verdict == "wrong_answer" and example_result is not None
          and hint["hint_tier"] is not None and hint["hint_tier"] == hint["hint_ceiling"]):
        concrete = _example_diff_hint(example_result, output_file)
        if concrete:
            hint = {**hint, "hint_text": concrete}

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
    result["traceback"] = _traceback_for(test_results)
    return result
