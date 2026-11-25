"""Task folder <-> question row (backend/task_import.py) and the import/export endpoints."""

import io
import os
import zipfile

import pytest
from fastapi.testclient import TestClient

from backend import store, task_format as tf, task_import as ti
from backend.main import app

EXAMPLE = os.path.join(os.path.dirname(__file__), "fixtures", "pandas-sales-summary")

client = TestClient(app)


def row_of(fields: dict) -> dict:
    """What store.get_question_row() would return for these fields."""
    qid = store.create_question(fields)
    row = store.get_question_row(qid)
    store.delete_question(qid)
    return row


def zip_dir(path: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for root, _dirs, names in os.walk(path):
            for name in names:
                full = os.path.join(root, name)
                z.write(full, os.path.relpath(full, os.path.dirname(path)))
    return buf.getvalue()


def test_example_task_loads():
    spec = tf.load_task_dir(EXAMPLE)
    assert spec.grading == "tests" and spec.editable == ["solution.py"]
    assert len(spec.files_with_role("test")) == 1 and len(spec.files_with_role("hidden_test")) == 1
    assert spec.extra_packages == ["pandas"]


def test_tests_task_becomes_a_question_and_exports_back():
    spec = tf.load_task_dir(EXAMPLE)
    fields = ti.question_fields(spec)
    assert fields["grading_mode"] == "tests" and fields["test_cases"] == []
    assert fields["starter_code"].startswith("import pandas") and "fillna" in fields["reference_solution"]
    assert fields["hint_ladder"] == spec.hints and len(fields["hint_ladder"]) == 3
    assert fields["extra_packages"] == ["pandas"]
    row = row_of(fields)
    assert ti.spec_of_question(row) == spec
    assert tf.load_task_zip(tf.to_zip(ti.spec_of_question(row))) == spec


def test_setup_page_question_exports_and_reimports():
    """A stdout question as the setup page creates it: no starter (the language default),
    unnamed tests, a data file on one test, a hint ladder and an allow-list."""
    row = row_of({
        "title": "Sum of Integers", "prompt": "Print the sum.", "language": "python",
        "test_cases": [
            {"stdin": "1 2 3\n", "expected_stdout": "6", "files": []},
            {"stdin": "", "expected_stdout": "3", "files": [{"name": "numbers.txt", "content": "1 2\n"}]},
        ],
        "reference_solution": "print(sum(map(int, input().split())))",
        "extra_packages": ["numpy"], "hint_ladder": ["Read the input."], "line_limit": 50,
        "cpu_time_limit_s": 2, "memory_limit_kb": 64000, "duration_seconds": 300,
    })
    spec = ti.spec_of_question(row)
    again = tf.load_task_zip(tf.to_zip(spec))
    fields = ti.question_fields(again)
    for key in ("title", "prompt", "language", "test_cases", "reference_solution", "starter_code",
                "extra_packages", "hint_ladder", "line_limit", "cpu_time_limit_s", "memory_limit_kb",
                "duration_seconds", "output_file"):
        assert fields[key] == row[key], key
    assert [c.name for c in again.stdout_cases] == ["example", "test_01"]


def test_split_files_inverts_join_files():
    files = {"a.py": "x = 1\n", "b.py": "def f():\n    return 2\n"}
    assert ti.split_files(ti.join_files(files, ["a.py", "b.py"], "python"), ["a.py", "b.py"], "python") == files
    assert ti.split_files("x = 1\n", ["a.py"], "python") == {"a.py": "x = 1\n"}
    assert ti.split_files("no headers\n", ["a.py", "b.py"], "python") == {"a.py": "no headers\n"}


def test_join_files_one_file_is_itself_several_get_headers():
    assert ti.join_files({"a.py": "x = 1\n"}, ["a.py"], "python") == "x = 1\n"
    joined = ti.join_files({"b.py": "y = 2\n", "a.py": "x = 1\n"}, ["a.py", "b.py"], "python")
    assert joined == "# ===== a.py =====\nx = 1\n\n# ===== b.py =====\ny = 2\n"
    assert ti.join_files({"A.java": "a", "B.java": "b"}, [], "java").startswith("// ===== A.java")


# --- endpoints ---------------------------------------------------------------------------


def test_import_endpoint_creates_a_draft_and_export_round_trips():
    r = client.post("/api/lecturer/questions/import",
                    files={"file": ("pandas-sales-summary.zip", zip_dir(EXAMPLE), "application/zip")})
    assert r.status_code == 200, r.text
    q = r.json()
    assert q["status"] == "draft" and q["grading_mode"] == "tests" and not q["validated"]
    assert {f["role"] for f in q["task_files"]} == {"starter", "test", "hidden_test", "reference", "data", "wrong"}

    r = client.get(f"/api/lecturer/questions/{q['id']}/export")
    assert r.status_code == 200
    assert r.headers["content-disposition"] == 'attachment; filename="pandas-sales-summary.zip"'
    assert tf.load_task_zip(r.content) == tf.load_task_dir(EXAMPLE)
    store.delete_question(q["id"])


def test_reimport_replaces_the_draft_but_not_a_started_task(tmp_path):
    import shutil
    folder = tmp_path / "pandas-sales-summary"
    shutil.copytree(EXAMPLE, folder)
    post = lambda: client.post("/api/lecturer/questions/import",
                               files={"file": ("t.zip", zip_dir(str(folder)), "application/zip")}).json()
    first = post()
    assert first["replaced"] is False
    store.update_question(first["id"], {"validated": 1})
    (folder / "task.yaml").write_text((folder / "task.yaml").read_text().replace(
        "title: Revenue per region", "title: Revenue per region (fixed)"))
    second = post()
    assert (second["id"], second["replaced"], second["title"], second["validated"]) == (
        first["id"], True, "Revenue per region (fixed)", False)
    assert sum(q.get("task_meta", {}).get("id") == "pandas-sales-summary"
               for q in store.list_question_rows(status="draft", current_lecture_only=True)) == 1

    store.update_question(first["id"], {"status": "closed"})  # it ran: leave it alone
    third = post()
    assert third["replaced"] is False and third["id"] != first["id"]
    assert store.get_question_row(first["id"])["title"] == "Revenue per region (fixed)"
    for qid in (first["id"], third["id"]):
        store.delete_question(qid)


def test_import_endpoint_lists_every_problem():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("t/task.yaml", "title: T\nlanguage: python\ngrading: tests\n")
        z.writestr("t/starter/solution.py", "x = 1\n")
    r = client.post("/api/lecturer/questions/import", files={"file": ("t.zip", buf.getvalue(), "application/zip")})
    assert r.status_code == 400
    detail = r.json()["detail"]
    assert detail.startswith("This task folder can't be used:")
    for fragment in ("description is required", "reference/: missing", "tests/: no test files"):
        assert fragment in detail


def test_import_endpoint_rejects_non_zip():
    r = client.post("/api/lecturer/questions/import", files={"file": ("t.zip", b"nope", "application/zip")})
    assert r.status_code == 400 and "isn't a zip file" in r.json()["detail"]


def test_export_unknown_question():
    assert client.get("/api/lecturer/questions/nope/export").status_code == 404


@pytest.mark.parametrize("qid", ["sum-ints"])
def test_seeded_question_exports(qid):
    r = client.get(f"/api/lecturer/questions/{qid}/export")
    spec = tf.load_task_zip(r.content)
    assert spec.grading == "stdout" and len(spec.stdout_cases) == 5
    assert not spec.files_with_role("starter")  # the seed has no starter: the language default


# --- checking wrong solutions -------------------------------------------------------------


def fake_runner(failing_by_code):
    """run_tests stand-in: every test passes unless the solution's text is in
    failing_by_code, which says which tests that code fails."""
    from backend.task_runner import TestResult
    names = [("tests/test_sales.py", "test_revenue_column", "visible"),
             ("tests/test_sales.py", "test_largest_region_first", "visible"),
             ("hidden_tests/test_sales_hidden.py", "test_missing_units_count_as_zero", "hidden"),
             ("hidden_tests/test_sales_hidden.py", "test_uses_the_dataframe_it_is_given", "hidden")]

    def run(task, files, include_hidden=True):
        failing = failing_by_code.get(files.get("solution.py"), set())
        return [TestResult(id=f"{f}::{n}", name=n, file=f, visibility=v,
                           outcome="failed" if n in failing else "passed") for f, n, v in names]
    return run


def test_validation_checks_each_wrong_solution(monkeypatch):
    from backend import main, task_runner
    spec = tf.load_task_dir(EXAMPLE)
    qid = store.create_question(ti.question_fields(spec))
    q = store.get_question_row(qid)
    wrong = task_runner.wrong_solutions(q)
    assert set(wrong) == {"forgot_fillna", "sorted_ascending", "reads_the_file_again"}
    starter = task_runner.starter_files(q)["solution.py"]

    caught = {starter: {"test_revenue_column"},
              wrong["forgot_fillna"]["solution.py"]: {"test_missing_units_count_as_zero"},
              wrong["sorted_ascending"]["solution.py"]: {"test_largest_region_first"},
              wrong["reads_the_file_again"]["solution.py"]: {"test_revenue_column"}}
    monkeypatch.setattr(task_runner, "run_tests", fake_runner(caught))
    out = client.post(f"/api/lecturer/questions/{qid}/validate").json()
    checks = {c["name"]: c for c in out["wrong_checks"]}
    assert checks["forgot_fillna"]["ok"] and checks["sorted_ascending"]["ok"]
    # task.yaml says this one must fail test_uses_the_dataframe_it_is_given:
    assert not checks["reads_the_file_again"]["ok"]
    assert "should fail test_uses_the_dataframe_it_is_given" in checks["reads_the_file_again"]["message"]
    assert out["validated"] is False

    del caught[wrong["forgot_fillna"]["solution.py"]]  # now it slips through every test
    out = client.post(f"/api/lecturer/questions/{qid}/validate").json()
    assert {c["name"]: c["message"] for c in out["wrong_checks"]}["forgot_fillna"] == (
        "forgot_fillna passes every test, so the tests don't catch this mistake.")
    store.delete_question(qid)


def test_wrong_solutions_never_reach_students():
    from backend import main
    q = {**ti.question_fields(tf.load_task_dir(EXAMPLE)), "status": "live"}
    paths = [f["path"] for f in main._workspace(q, with_content=True)]
    assert paths == ["solution.py", "tests/test_sales.py", "data/sales.csv"]
    from backend import task_runner
    assert not any("wrong" in p for p in task_runner.sandbox_files(q, {}, include_hidden=True))


def test_example_task_download(monkeypatch):
    r = client.get("/api/lecturer/example_task")
    assert r.status_code == 200
    assert r.headers["content-disposition"] == 'attachment; filename="pandas-sales-summary.zip"'
    assert tf.load_task_zip(r.content) == tf.load_task_dir(EXAMPLE)
    from backend import main
    monkeypatch.setattr(main, "EXAMPLE_TASK_DIR", "/nonexistent")
    assert client.get("/api/lecturer/example_task").status_code == 404



# --- code-review fixes ---------------------------------------------------------------------


def _example_question(**overrides):
    raw = tf.read_dir(EXAMPLE)
    raw.update({k: v.encode() for k, v in overrides.items()})
    qid = store.create_question(ti.question_fields(tf.parse_task(raw, default_id="pandas-sales-summary")))
    return qid, store.get_question_row(qid)


def _caught(q, starter_fails=True):
    from backend import task_runner
    must = q["task_meta"]["wrong_solutions"]
    caught = {w["solution.py"]: set(must[name]) for name, w in task_runner.wrong_solutions(q).items()}
    if starter_fails:
        caught[task_runner.starter_files(q)["solution.py"]] = {"test_revenue_column"}
    return caught


def test_validation_counts_a_skipped_test_as_passing(monkeypatch):
    from backend import task_runner
    from backend.task_runner import TestResult
    qid, q = _example_question()
    caught = _caught(q)

    def run(task, files, include_hidden=True):
        out = fake_runner(caught)(task, files, include_hidden)
        if files.get("solution.py") not in caught:  # the reference: one test is skipped
            out[1] = TestResult(id=out[1].id, name=out[1].name, file=out[1].file, visibility="visible",
                                outcome="skipped")
        return out
    monkeypatch.setattr(task_runner, "run_tests", run)
    out = client.post(f"/api/lecturer/questions/{qid}/validate").json()
    assert out["validated"] is True, out
    assert len(store.get_question_row(qid)["task_meta"]["test_ids"]) == 4
    store.delete_question(qid)


def test_an_empty_starter_that_passes_everything_is_caught(monkeypatch):
    from backend import task_runner
    qid, q = _example_question(**{"starter/solution.py": ""})
    assert q["starter_code"] == ""
    # Every test passes on the empty starter (unknown code passes in the fake runner).
    monkeypatch.setattr(task_runner, "run_tests", fake_runner(_caught(q, starter_fails=False)))
    out = client.post(f"/api/lecturer/questions/{qid}/validate").json()
    assert out["validated"] is False
    assert out["starter_problem"]["blocking"] and "already pass every test" in out["starter_problem"]["message"]
    store.delete_question(qid)


def test_workspace_only_for_tasks_that_ran():
    qid, _q = _example_question()
    for status, code in (("draft", 404), ("skipped", 404), ("live", 200), ("closed", 200)):
        store.update_question(qid, {"status": status})
        assert client.get(f"/api/lecture/questions/{qid}/workspace").status_code == code, status
        assert client.get(f"/api/lecture/questions/{qid}/workspace/tests/test_sales.py").status_code == code, status
    store.delete_question(qid)
