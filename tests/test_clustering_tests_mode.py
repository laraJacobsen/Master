"""Wrong-answer clustering, evidence and student-facing views for test-graded tasks:
the failing-test set as the first-level signature, diff sub-clustering below it."""

import json

from backend import aggregation as ag
from backend.ai_feedback import TESTS_HIDDEN_HINT, judge_and_feedback
from backend.main import _student_test_view
from backend.task_runner import TestResult, as_dicts

V1, V2, H1 = "tests/test_s.py::test_a", "tests/test_s.py::test_b", "hidden_tests/test_h.py::test_c"

REFERENCE = "def total(xs):\n    return sum(x for x in xs if x is not None)\n"
SKIPS_NONE_WRONG = "def total(xs):\n    return sum(xs)\n"
OFF_BY_ONE = "def total(xs):\n    return sum(x for x in xs[1:] if x is not None)\n"


def results(failing: dict) -> list:
    """failing: {test id: message}; every other test passes."""
    out = []
    for tid in (V1, V2, H1):
        msg = failing.get(tid)
        out.append(TestResult(
            id=tid, name=tid.rsplit("::", 1)[1], file=tid.split("::")[0],
            visibility="hidden" if tid.startswith("hidden") else "visible",
            outcome="failed" if msg else "passed", message=msg or "",
            error_type="AssertionError" if msg else None,
        ))
    return as_dicts(out)


_ids = iter(range(1, 10_000))


def row(student: str, code: str, failing: dict, question_id: str = "q") -> dict:
    return {"id": next(_ids), "student_name": student, "question_id": question_id, "source_code": code,
            "exec_verdict": "wrong_answer", "raw_test_results": json.dumps(results(failing))}


def test_failing_test_signature_is_the_sorted_failing_set():
    r = row("a", OFF_BY_ONE, {H1: "x", V1: "assert 5 == 6"})
    assert ag._failing_test_signature(r) == (H1, V1)
    assert ag._output_signature(r) is None


def test_stdout_rows_keep_the_output_signature():
    stdout_row = {"raw_test_results": json.dumps([{"case_index": 0, "passed": False, "stdout": "5 "}])}
    assert ag._failing_test_signature(stdout_row) is None
    assert ag._output_signature(stdout_row) == ("5",)


def test_same_failing_set_same_bug_is_one_group():
    rows = [row(s, OFF_BY_ONE, {V1: "assert 5 == 6"}) for s in ("a", "b", "c")]
    groups = ag._group_wrong_answers(rows, REFERENCE, "q")
    assert [len(g) for g in groups] == [3]


def test_different_failing_sets_never_merge_even_with_identical_code():
    rows = [row("a", OFF_BY_ONE, {V1: "assert 5 == 6"}), row("b", OFF_BY_ONE, {H1: "assert 0 == 1"})]
    groups = ag._group_wrong_answers(rows, REFERENCE, "q")
    assert sorted(len(g) for g in groups) == [1, 1]


def test_same_failing_set_different_bugs_are_split_by_the_diff():
    rows = [row("a", OFF_BY_ONE, {V1: "assert 5 == 6"}), row("b", OFF_BY_ONE, {V1: "assert 5 == 6"}),
            row("c", SKIPS_NONE_WRONG, {V1: "TypeError"}), row("d", SKIPS_NONE_WRONG, {V1: "TypeError"})]
    groups = ag._group_wrong_answers(rows, REFERENCE, "q")
    assert sorted(sorted(r["student_name"] for r in g) for g in groups) == [["a", "b"], ["c", "d"]]


def test_shared_failing_tests_evidence_for_the_lecturer_includes_hidden():
    group = [row("a", OFF_BY_ONE, {V2: "assert 1 == 2", H1: "assert 0 == 1"}),
             row("b", OFF_BY_ONE, {V2: "assert 3 == 2", H1: "assert 0 == 1"})]
    shared = ag._shared_failing_cases(group)
    assert [(c["test_name"], c["visibility"], c["same_message"]) for c in shared] == [
        ("test_b", "visible", False), ("test_c", "hidden", True)]
    assert shared[1]["message"] == "assert 0 == 1"


def test_distinguishing_case_uses_the_test_not_just_the_empty_stdin():
    a = [{"test_id": V1, "stdin": "", "stdout": "m"}, {"test_id": V2, "stdin": "", "stdout": "m"}]
    b = [{"test_id": V1, "stdin": "", "stdout": "m"}]
    assert ag._distinguishing_case(a, [b])["test_id"] == V2


def test_most_common_wrong_output_reports_the_test_and_message():
    rows = [row("a", OFF_BY_ONE, {V2: "assert 1 == 2"}), row("b", OFF_BY_ONE, {V2: "assert 1 == 2"}),
            row("c", OFF_BY_ONE, {V1: "assert 9 == 2"})]
    top = ag._most_common_wrong_output(rows)
    assert (top["test_name"], top["message"], top["students"]) == ("test_b", "assert 1 == 2", 2)


def test_cluster_submissions_end_to_end(monkeypatch):
    from backend import store
    qid = store.create_question({"title": "Clustering tests mode", "prompt": "p", "language": "python",
                                 "test_cases": [], "reference_solution": REFERENCE, "grading_mode": "tests"})
    base = {"question_id": qid, "language": "python", "attempt_number": 1, "tests_total": 3, "verdict": "partially_correct",
            "error_type": None, "exec_verdict": "wrong_answer", "rejection_reason": None, "feedback": "",
            "discussion_point": None}
    for student, code, failing in (("a", OFF_BY_ONE, {V1: "x"}), ("b", OFF_BY_ONE, {V1: "x"}),
                                   ("c", OFF_BY_ONE, {H1: "y"})):
        store.save_submission({**base, "student_name": student, "source_code": code,
                               "tests_passed": 2, "raw_test_results": json.dumps(results(failing))})
    monkeypatch.setattr(ag, "_llm_available", lambda: False)
    clusters = [c for c in ag.cluster_submissions(qid) if c["exec_verdict"] == "wrong_answer"]
    assert sorted(c["count"] for c in clusters) == [1, 2]
    by_count = {c["count"]: c["failing_tests"] for c in clusters}
    assert by_count[2] == [{"name": "test_a", "visibility": "visible"}]
    assert by_count[1] == [{"name": "test_c", "visibility": "hidden"}]
    store.delete_question(qid)


# --- what students see --------------------------------------------------------------------


def test_shared_example_hides_hidden_tests_from_the_class(monkeypatch):
    sub = {"source_code": OFF_BY_ONE, "verdict": "partially_correct",
           "raw_test_results": json.dumps(results({H1: "assert secret == 42"}))}
    monkeypatch.setattr(ag.store, "get_submission", lambda _id: sub)
    shown = ag._shared_example(1)
    assert shown["failing_test"] is None
    assert shown["hidden_tests"] == {"total": 1, "failed": 1}
    assert "secret" not in json.dumps(shown) and "test_c" not in json.dumps(shown)


def test_student_view_shows_prints_of_visible_tests_only():
    rs = results({})
    rs[0]["output"] = "debug: 5"
    rs[2]["output"] = "hidden input was 42"
    view = _student_test_view(rs)
    assert view["test_results"][0]["output"] == "debug: 5"
    assert "42" not in json.dumps(view)


def test_student_view_shows_top_level_prints_from_visible_test_files_only():
    rs = results({})
    rs[0]["load_output"] = "loading my solution"
    rs[2]["load_output"] = "hidden module printed this"
    view = _student_test_view(rs)
    assert view["load_output"] == [{"file": "tests/test_s.py", "output": "loading my solution"}]
    assert "hidden module" not in json.dumps(view)


def test_student_view_counts_hidden_tests_only():
    view = _student_test_view(results({V1: "assert 5 == 6", H1: "assert secret == 42"}))
    assert [(t["name"], t["passed"], t["message"]) for t in view["test_results"]] == [
        ("test_a", False, "assert 5 == 6"), ("test_b", True, "")]
    assert view["hidden_tests"] == {"total": 1, "failed": 1, "hints": []}
    assert "secret" not in json.dumps(view) and "test_c" not in json.dumps(view)


def test_hidden_test_hint_shows_only_when_that_test_fails_and_never_its_name():
    hints = {"test_c": "Checks a list with a missing value."}
    failing = _student_test_view(results({H1: "assert secret == 42"}), hints)
    assert failing["hidden_tests"]["hints"] == ["Checks a list with a missing value."]
    assert "test_c" not in json.dumps(failing) and "secret" not in json.dumps(failing)
    assert _student_test_view(results({}), hints)["hidden_tests"]["hints"] == []


# --- verdict and hints ----------------------------------------------------------------------


def judge(failing: dict, attempt: int = 1, ladder=None) -> dict:
    return judge_and_feedback("p", "code", results(failing), attempt_number=attempt, hint_ladder=ladder,
                              grading_mode="tests")


def test_every_test_counts_toward_the_verdict():
    assert judge({})["verdict"] == "correct" and judge({})["tests_total"] == 3
    hidden_only = judge({H1: "x"})
    assert (hidden_only["verdict"], hidden_only["tests_passed"], hidden_only["exec_verdict"]) == (
        "partially_correct", 2, "wrong_answer")


def test_tests_mode_hints_name_the_visible_test_and_escalate():
    tiers = [judge({V2: "assert 1 == 2", H1: "x"}, attempt)["feedback"] for attempt in (1, 2, 3, 4)]
    assert tiers[0].startswith("Your code runs, but 2 tests fail. Start with test_b")
    assert "tests/test_s.py" in tiers[1]
    assert tiers[2] == tiers[3] and '"assert 1 == 2"' in tiers[2]
    assert all("test_c" not in t for t in tiers)


def test_tests_mode_hints_when_only_hidden_tests_fail():
    first, second = judge({H1: "assert secret"}, 1)["feedback"], judge({H1: "assert secret"}, 2)["feedback"]
    assert first.startswith("Every visible test passes, but 1 hidden test fails.")
    assert second == TESTS_HIDDEN_HINT and "secret" not in first + second


def test_lecturer_ladder_still_wins():
    assert judge({V1: "x"}, ladder=["Own hint."])["feedback"] == "Own hint."


def test_crash_keeps_the_error_specific_hint():
    crash = as_dicts([TestResult(id=V1, name="test_a", file="tests/test_s.py", visibility="visible", outcome="failed",
                                 message="KeyError: 'revenue'", details="E   KeyError: 'revenue'", error_type="KeyError")])
    fb = judge_and_feedback("p", "c", crash, grading_mode="tests")
    assert (fb["exec_verdict"], fb["error_type"]) == ("runtime_error", "KeyError")


def test_stdout_groups_have_no_failing_tests():
    stdout_row = {"raw_test_results": json.dumps([{"case_index": 0, "passed": False, "stdout": "5"}])}
    assert ag._failing_tests_of_group([stdout_row]) is None



def test_shown_multi_file_attempt_keeps_file_headers_without_comments(monkeypatch):
    """The projector's Run splits a shown attempt back into files on the headers, so
    stripping comments must not take the headers with them."""
    files = {"solution.py": "def a():  # my note\n    return 1\n", "helpers.py": "# helper\nB = 2\n"}
    sub = {"source_code": "joined", "language": "python", "verdict": "partially_correct",
           "files": json.dumps(files), "raw_test_results": json.dumps(results({V1: "assert 0 == 1"}))}
    monkeypatch.setattr(ag.store, "get_submission", lambda _id: sub)
    shown = ag._shared_example(1)["source_code"]
    assert "# ===== solution.py =====" in shown and "# ===== helpers.py =====" in shown
    assert "my note" not in shown and "# helper" not in shown
    from backend import task_import
    assert task_import.split_files(shown, ["solution.py", "helpers.py"], "python") == {
        "solution.py": "def a():\n    return 1\n", "helpers.py": "B = 2\n"}
