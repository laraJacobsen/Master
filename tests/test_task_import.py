"""Task folder <-> question row (backend/task_import.py) and the import/export endpoints."""

import io
import os
import zipfile

import pytest
from fastapi.testclient import TestClient

from backend import store, task_format as tf, task_import as ti
from backend.main import app

EXAMPLE = os.path.join(os.path.dirname(__file__), "..", "tasks", "pandas-sales-summary")

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
    assert {f["role"] for f in q["task_files"]} == {"starter", "test", "hidden_test", "reference", "data"}

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
