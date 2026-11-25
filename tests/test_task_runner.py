"""JUnit parsing and crash mapping (backend/task_runner.py), against real Judge0 runs of
the example task saved in tests/fixtures/judge0_runs.json (make_judge0_runs.py regenerates it)."""

import json
import os
import re

import pytest

from backend import hints, task_format, task_import, task_runner as tr

with open(os.path.join(os.path.dirname(__file__), "fixtures", "judge0_runs.json")) as _f:
    RUNS = json.load(_f)
EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "pandas-sales-summary")

TASK = task_import.question_fields(task_format.load_task_dir(EXAMPLE))

VISIBLE = ["tests/test_sales.py::test_revenue_column", "tests/test_sales.py::test_keeps_every_row",
           "tests/test_sales.py::test_largest_region_first"]
HIDDEN = ["hidden_tests/test_sales_hidden.py::test_missing_units_count_as_zero",
          "hidden_tests/test_sales_hidden.py::test_uses_the_dataframe_it_is_given"]
EXPECTED = [{"id": i, "visibility": "visible"} for i in VISIBLE] + [{"id": i, "visibility": "hidden"} for i in HIDDEN]


def run_of(scenario: str) -> dict:
    return RUNS[scenario]


def results(scenario: str, expected=EXPECTED, include_hidden=True) -> list:
    run = run_of(scenario)
    marker = re.search(r"@@REPORT-[0-9a-f]{24}@@", run["stdout"] or "")
    return tr.results_from_run(run, marker.group(0) if marker else "@@none@@", expected, include_hidden)


def classified(scenario: str) -> tuple:
    return hints.classify_submission(tr.as_dicts(results(scenario)), language="python")


def failing(rs) -> set:
    return {r.id for r in rs if not r.passed}


# --- parsing real reports ---------------------------------------------------------------


def test_all_pass_in_reference_order_visible_first():
    rs = results("all_pass", expected=None)
    assert [r.id for r in rs] == VISIBLE + HIDDEN
    assert all(r.outcome == "passed" for r in rs)
    assert [r.visibility for r in rs] == ["visible"] * 3 + ["hidden"] * 2
    assert tr.expected_test_ids(rs) == EXPECTED
    assert classified("all_pass") == ("pass", None)


def test_starter_failures_have_short_messages_and_types():
    rs = {r.name: r for r in results("starter")}
    assert rs["test_keeps_every_row"].outcome == "passed"
    revenue = rs["test_revenue_column"]
    assert (revenue.outcome, revenue.error_type) == ("failed", "AssertionError")
    assert revenue.message.startswith("assert 'revenue' in")
    assert rs["test_missing_units_count_as_zero"].error_type == "KeyError"
    assert rs["test_missing_units_count_as_zero"].message == "KeyError: 'revenue'"
    assert rs["test_largest_region_first"].error_type == "AttributeError"
    assert all(len(r.message) <= 300 and len(r.details) <= 2000 for r in rs.values())
    # The first failing test is an assertion: a wrong answer, not a crash.
    assert classified("starter") == ("wrong_answer", None)


def test_hidden_only_failure_is_a_wrong_answer_with_one_failing_test():
    rs = results("wrong_forgot_fillna")
    assert failing(rs) == {HIDDEN[0]}
    assert classified("wrong_forgot_fillna") == ("wrong_answer", None)


def test_exception_inside_a_test_maps_to_runtime_error_with_its_name():
    run = [r for r in results("starter") if r.error_type == "KeyError"]
    assert hints.classify_submission(tr.as_dicts(run), language="python") == ("runtime_error", "KeyError")


@pytest.mark.parametrize("scenario, expected_class", [
    ("syntax_error", ("syntax_error", None)),
    ("import_error", ("runtime_error", "ImportError")),
    ("missing_package", ("runtime_error", "ModuleNotFoundError")),
    ("per_test_timeout", ("timeout", None)),
    ("run_timeout", ("timeout", None)),
    ("memory", ("oom", None)),
    ("exits_early", ("runtime_error", "Unknown")),
])
def test_crashes_map_to_existing_classes(scenario, expected_class):
    assert classified(scenario) == expected_class


def test_collection_error_fails_every_test_of_that_file_with_the_error():
    rs = results("syntax_error")
    assert [r.id for r in rs] == VISIBLE + HIDDEN
    assert all(r.outcome == "error" and r.error_type == "SyntaxError" for r in rs)
    assert "SyntaxError" in rs[0].message and "solution.py" in rs[0].details


def test_collection_error_without_known_test_ids_reports_the_modules():
    rs = results("import_error", expected=None)
    assert [r.id for r in rs] == ["tests/test_sales.py", "hidden_tests/test_sales_hidden.py"]
    assert rs[0].message.startswith("ImportError: cannot import name 'load_sales'")


def test_per_test_timeout_only_fails_the_slow_tests():
    rs = results("per_test_timeout")
    assert failing(rs) == {VISIBLE[2], HIDDEN[1]}
    assert {r.error_type for r in rs if not r.passed} == {"Timeout"}


def test_whole_run_killed_fails_every_test_as_timeout():
    rs = results("run_timeout")
    assert len(rs) == 5 and all(r.error_type == "Timeout" and r.outcome == "error" for r in rs)
    assert rs[0].run_status == "Time Limit Exceeded"


def test_run_without_a_report_without_known_ids_is_one_error():
    rs = results("exits_early", expected=None)
    assert [r.id for r in rs] == ["(test run)"]
    assert "stopped before" in rs[0].message


def test_prints_are_kept_per_test_without_pytest_headers():
    rs = {r.name: r for r in results("prints")}
    assert rs["test_revenue_column"].output == "rows: 12"
    assert rs["test_missing_units_count_as_zero"].output == "rows: 12"  # hidden: kept for the lecturer
    assert rs["test_uses_the_dataframe_it_is_given"].output == ""  # never calls load_sales
    assert all(r.passed for r in rs.values())
    assert tr.as_dicts(list(rs.values()))[0]["output"] == "rows: 12"


def test_top_level_prints_land_on_the_first_test_of_the_importing_file():
    rs = results("prints_top_level")
    assert rs[0].load_output == "loading my solution"
    assert all(r.load_output == "" for r in rs[1:])
    assert rs[0].output == ""  # printed at import, not during the test
    assert tr.as_dicts(rs)[0]["load_output"] == "loading my solution"


def test_load_output_parsing_is_defensive():
    assert tr._load_outputs(None) == {} and tr._load_outputs("not json") == {}
    assert tr._load_outputs('[{"file": "tests/t.py", "output": "a"}, {"file": 3}]') == {"tests/t.py": "a"}


def test_long_output_is_cut():
    assert tr._short_tail("x" * 5000, 100).endswith("... (more output cut)")
    assert tr._short_tail("----- Captured stdout call -----\nhello\n", 100) == "hello"


def test_visible_only_run():
    rs = results("wrong_forgot_fillna", include_hidden=False)
    assert [r.id for r in rs] == VISIBLE and all(r.passed for r in rs)


def test_result_dict_shape_is_what_stdout_results_have():
    d = tr.as_dicts(results("starter"))[2]
    for key in ("case_index", "passed", "status_description", "stdout", "stderr", "exit_code", "expected_stdout"):
        assert key in d
    assert d["case_index"] == 2 and d["test_id"] == VISIBLE[2] and d["visibility"] == "visible"
    assert d["stderr"].endswith("AttributeError: 'NoneType' object has no attribute 'index'")


# --- parsing edge cases (hand-written XML) -------------------------------------------------


def test_class_tests_skips_and_xunit2_without_file_attribute():
    xml = """<testsuites><testsuite>
      <testcase classname="hidden_tests.test_x.TestThing" name="test_a" time="0.1"/>
      <testcase classname="tests.test_y" name="test_b[1-2]" time="0.0"><skipped message="not today"/></testcase>
      <testcase classname="tests.test_y" name="test_c"><failure message="Failed: nope">tb</failure></testcase>
    </testsuite></testsuites>"""
    rs, coll = tr.parse_junit_xml(xml)
    assert coll == {}
    assert [r.id for r in rs] == ["hidden_tests/test_x.py::TestThing::test_a", "tests/test_y.py::test_b[1-2]",
                                  "tests/test_y.py::test_c"]
    assert rs[0].visibility == "hidden" and rs[1].outcome == "skipped" and rs[1].passed
    assert rs[2].error_type == "Failed" and tr.as_dicts(rs)[2]["status_description"] == "Wrong Answer"


def test_unknown_reported_tests_are_dropped_and_missing_ones_error():
    xml = """<testsuites><testsuite>
      <testcase classname="tests.test_sales" file="tests/test_sales.py" name="test_revenue_column"/>
      <testcase classname="tests.test_evil" file="tests/test_evil.py" name="test_free_pass"/>
    </testsuite></testsuites>"""
    rs = tr.assemble(xml, {"status_description": "Accepted", "exit_code": 0}, "", EXPECTED)
    assert [r.id for r in rs] == VISIBLE + HIDDEN
    assert rs[0].passed and not any(r.passed for r in rs[1:])


def test_garbage_report_counts_as_no_report():
    rs = tr.assemble("<not xml", {"status_description": "Accepted", "exit_code": 0}, "", EXPECTED)
    assert len(rs) == 5 and not any(r.passed for r in rs)


# --- student files -------------------------------------------------------------------------


MARKED = {
    **TASK,
    "task_meta": {**TASK["task_meta"], "editable": ["solution.py"], "markers": {"begin": "# BEGIN", "end": "# END"}},
    "task_files": [
        {"path": "solution.py", "role": "starter", "content": "import x\n# BEGIN\npass\n# END\nprint(1)\n"},
        {"path": "helpers.py", "role": "starter", "content": "H = 1\n"},
        {"path": "test_a.py", "role": "test", "content": "def test_a(): pass\n"},
        {"path": "test_b.py", "role": "hidden_test", "content": "def test_b(): pass\n"},
        {"path": "d.csv", "role": "data", "content": "x\n"},
        {"path": "solution.py", "role": "reference", "content": "ref\n"},
    ],
}


def test_prepare_submission_splices_markers_and_refuses_strangers():
    student = "import evil\n# BEGIN\nreturn 42\n# END\nprint('changed')\n"
    assert tr.prepare_submission(MARKED, {"solution.py": student}) == {
        "solution.py": "import x\n# BEGIN\nreturn 42\n# END\nprint(1)\n"}
    with pytest.raises(tr.SubmissionFilesError, match="isn't a file you can edit"):
        tr.prepare_submission(MARKED, {"helpers.py": "H = 2\n"})
    with pytest.raises(tr.SubmissionFilesError, match="missing or changed"):
        tr.prepare_submission(MARKED, {"solution.py": "return 42\n"})
    assert tr.prepare_submission(MARKED, {}) == {"solution.py": MARKED["task_files"][0]["content"]}


def test_sandbox_layout():
    files = tr.sandbox_files(MARKED, {"solution.py": "mine\n"}, include_hidden=False)
    assert files.pop("_classloop_collect.py").startswith("import json")
    assert files == {"solution.py": "mine\n", "helpers.py": "H = 1\n", "tests/test_a.py": "def test_a(): pass\n",
                     "data/d.csv": "x\n"}
    assert "hidden_tests/test_b.py" in tr.sandbox_files(MARKED, {}, include_hidden=True)


# --- code-review fixes ---------------------------------------------------------------------


def test_one_broken_test_file_does_not_fail_the_others():
    """A hidden test file importing a function the student doesn't have: the visible
    test still runs and passes (pytest --continue-on-collection-errors)."""
    expected = [{"id": "tests/test_a.py::test_a", "visibility": "visible"},
                {"id": "hidden_tests/test_b.py::test_b", "visibility": "hidden"}]
    rs = results("collection_error_in_one_file", expected=expected)
    assert [(r.name, r.outcome) for r in rs] == [("test_a", "passed"), ("test_b", "error")]
    assert rs[1].error_type == "ImportError"
    assert hints.classify_submission(tr.as_dicts(rs), language="python") == ("runtime_error", "ImportError")


def test_lecturer_run_of_whole_files_skips_the_marker_splice():
    shown = {"solution.py": "import x\nreturn 42\nprint(1)\n"}  # markers stripped with the comments
    with pytest.raises(tr.SubmissionFilesError):
        tr.prepare_submission(MARKED, shown)
    assert tr.prepare_submission(MARKED, shown, splice_markers=False) == shown
