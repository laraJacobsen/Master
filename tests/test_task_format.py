"""Task-folder loader and validation (backend/task_format.py)."""

import io
import os
import stat
import zipfile

import pytest

from backend import task_format as tf
from backend.task_format import TaskFormatError

TASK_YAML = """\
title: Revenue per region
description: |
  Sum revenue per region.
language: python
grading: tests
editable: [solution.py]
time_limit_s: 4
memory_limit_mb: 200
"""

STARTER = "import pandas as pd\n\n\ndef revenue(path):\n    # TODO\n    pass\n"
REFERENCE = "import pandas as pd\n\n\ndef revenue(path):\n    return pd.read_csv(path)['x'].sum()\n"
TEST = "from solution import revenue\n\n\ndef test_sum():\n    assert revenue('data/d.csv') == 3\n"
HIDDEN = "from solution import revenue\n\n\nclass TestHidden:\n    def test_type(self):\n        assert revenue('data/d.csv') > 0\n"


def pytest_task(**overrides) -> dict:
    files = {
        "task.yaml": TASK_YAML,
        "starter/solution.py": STARTER,
        "starter/helpers.py": "def nothing():\n    pass\n",
        "reference/solution.py": REFERENCE,
        "tests/test_visible.py": TEST,
        "hidden_tests/test_hidden.py": HIDDEN,
        "data/d.csv": "x\n1\n2\n",
        "requirements.txt": "pandas==2.2.3\nnumpy  # any version\n",
    }
    files.update(overrides)
    return {k: v.encode() for k, v in files.items() if v is not None}


def stdout_task(**overrides) -> dict:
    files = {
        "task.yaml": "title: Sum\ndescription: Sum the numbers.\nlanguage: python\ngrading: stdout\n",
        "starter/solution.py": "line = input()\n",
        "reference/solution.py": "print(sum(map(int, input().split())))\n",
        "tests/example/stdin.txt": "1 2 3\n",
        "tests/example/expected_stdout.txt": "6\n",
        "hidden_tests/b/stdin.txt": "5\n",
        "hidden_tests/b/expected_stdout.txt": "5\n",
        "hidden_tests/a/stdin.txt": "",
        "hidden_tests/a/expected_stdout.txt": "0\n",
        "hidden_tests/a/files/numbers.txt": "1 2\n",
    }
    files.update(overrides)
    return {k: v.encode() for k, v in files.items() if v is not None}


def problems_of(raw: dict) -> list[str]:
    with pytest.raises(TaskFormatError) as e:
        tf.parse_task(raw)
    return e.value.problems


def assert_problem(raw: dict, *fragments: str):
    problems = problems_of(raw)
    for fragment in fragments:
        assert any(fragment in p for p in problems), f"{fragment!r} not in {problems}"


# --- valid tasks --------------------------------------------------------------------


def test_tests_task_loads():
    spec = tf.parse_task(pytest_task(), default_id="revenue")
    assert (spec.id, spec.title, spec.language, spec.grading) == ("revenue", "Revenue per region", "python", "tests")
    assert spec.description == "Sum revenue per region."
    assert spec.editable == ["solution.py"]
    assert spec.cpu_time_limit_s == 4 and spec.memory_limit_kb == 200_000
    assert spec.requirements == ["pandas==2.2.3", "numpy"]
    assert spec.extra_packages == ["numpy", "pandas"]
    roles = {(f.role, f.sandbox_path) for f in spec.files}
    assert roles == {
        ("starter", "solution.py"), ("starter", "helpers.py"), ("reference", "solution.py"),
        ("test", "tests/test_visible.py"), ("hidden_test", "hidden_tests/test_hidden.py"),
        ("data", "data/d.csv"),
    }


def test_defaults_and_editable_defaults_to_every_starter_file():
    raw = pytest_task(**{
        "task.yaml": "title: T\ndescription: D\nlanguage: python\ngrading: tests\n",
        "starter/helpers.py": None,
    })
    spec = tf.parse_task(raw)
    assert spec.editable == ["solution.py"]
    assert (spec.cpu_time_limit_s, spec.memory_limit_kb, spec.test_timeout_s, spec.duration_seconds) == (5, 128000, 2, 600)


def test_stdout_task_loads_visible_case_first_hidden_sorted():
    spec = tf.parse_task(stdout_task())
    assert [(c.name, c.visible) for c in spec.stdout_cases] == [("example", True), ("a", False), ("b", False)]
    assert spec.stdout_cases[1].files == [{"name": "numbers.txt", "content": "1 2\n"}]
    assert spec.stdout_cases[1].stdin == ""


def test_stdout_task_without_starter_uses_reference_file_name():
    spec = tf.parse_task(stdout_task(**{"starter/solution.py": None}))
    assert spec.editable == ["solution.py"] and not spec.files_with_role("starter")


def test_junk_files_from_zipping_are_ignored():
    raw = pytest_task()
    data = zip_of({**raw, "__MACOSX/._task.yaml": b"\x00", "starter/__pycache__/x.pyc": b"\x00", ".DS_Store": b""})
    spec = tf.load_task_zip(data)
    assert {f.path for f in spec.files_with_role("starter")} == {"solution.py", "helpers.py"}


# --- broken tasks: clear, collected problems --------------------------------------------


def test_missing_task_yaml_lists_what_was_found():
    raw = pytest_task(**{"task.yaml": None})
    assert_problem(raw, "task.yaml is missing", "starter")


def test_invalid_yaml_reports_line():
    assert_problem(pytest_task(**{"task.yaml": "title: [unclosed\nlanguage: python\n"}), "not valid YAML (line")


def test_every_problem_is_reported_at_once():
    raw = pytest_task(**{
        "task.yaml": "language: cobol\ngrading: magic\ncolour: blue\n",
        "reference/solution.py": None,
    })
    problems = problems_of(raw)
    for fragment in ("title is required", "description is required", "language must be one of",
                     "grading must be one of", "unknown key(s) colour", "reference/: missing"):
        assert any(fragment in p for p in problems), (fragment, problems)


def test_tests_grading_not_supported_for_java_yet():
    raw = pytest_task(**{"task.yaml": TASK_YAML.replace("language: python", "language: java")})
    assert_problem(raw, "grading: tests isn't supported for java yet")


def test_limits_out_of_range():
    raw = pytest_task(**{"task.yaml": TASK_YAML.replace("memory_limit_mb: 200", "memory_limit_mb: 4096")})
    assert_problem(raw, "memory_limit_mb must be a number from 16 to 256")


def test_editable_file_must_exist_and_reference_must_match():
    raw = pytest_task(**{
        "task.yaml": TASK_YAML.replace("[solution.py]", "[solution.py, missing.py]"),
        "reference/extra.py": "x = 1\n",
    })
    assert_problem(raw, "editable lists missing.py, but starter/missing.py doesn't exist",
                   "reference/extra.py: not an editable file", "reference/missing.py: missing")


def test_files_outside_the_known_folders():
    assert_problem(pytest_task(**{"notes.md": "hi"}), "notes.md: files must be inside starter/")


def test_requirement_not_in_image_or_wrong_version():
    raw = pytest_task(**{"requirements.txt": "pandas==1.5.3\nscipy>=1.0\nnot a requirement!\n"})
    assert_problem(raw, '"pandas==1.5.3" doesn\'t match the runner image\'s pandas 2.2.3',
                   '"scipy" isn\'t in the runner image', "isn't a requirement line")


def test_requirement_ranges_that_include_the_pin_are_fine():
    spec = tf.parse_task(pytest_task(**{"requirements.txt": "pandas>=2.2,<3\nnumpy~=2.2\n"}))
    assert spec.extra_packages == ["numpy", "pandas"]


def test_needs_a_visible_test_with_test_functions():
    assert_problem(pytest_task(**{"tests/test_visible.py": None, "tests/conftest.py": "import pytest\n"}),
                   "tests/: no test files")
    assert_problem(pytest_task(**{"tests/test_visible.py": "def helper():\n    pass\n"}),
                   "tests/test_visible.py: no test functions")


def test_same_test_file_name_in_visible_and_hidden():
    assert_problem(pytest_task(**{"hidden_tests/test_visible.py": TEST}),
                   "hidden_tests/test_visible.py: same file name as a visible test")


def test_test_module_named_like_a_starter_file():
    assert_problem(pytest_task(**{"tests/solution.py": "x = 1\n"}), "tests/solution.py: same module name as a starter file")


def test_syntax_errors_reported_with_line_but_unfinished_starter_is_fine():
    raw = pytest_task(**{
        "tests/test_visible.py": "def test_x(:\n    pass\n",
        "starter/solution.py": "def revenue(path):\n    # TODO: finish me\n    return (\n",
    })
    problems = problems_of(raw)
    assert any(p.startswith("tests/test_visible.py: line 1:") for p in problems), problems
    assert not any(p.startswith("starter/solution.py") for p in problems), problems


def test_binary_file_is_rejected_with_a_reason():
    raw = pytest_task()
    raw["data/sheet.xlsx"] = b"PK\x03\x04\xff\xfe\x00"
    assert_problem(raw, "data/sheet.xlsx: not a UTF-8 text file")


def test_unsafe_names():
    raw = pytest_task()
    raw["data/my file.csv"] = b"x\n"
    raw["data/.hidden"] = b"x\n"
    problems = problems_of(raw)
    assert sum("use only letters, digits" in p for p in problems) == 2, problems


def test_reserved_and_colliding_starter_names():
    assert_problem(pytest_task(**{"starter/run": "#!/bin/bash\n", "starter/tests/x.py": "x = 1\n"}),
                   "starter/run: a name the grader uses", "starter/tests/x.py: would collide")


def test_stdout_needs_exactly_one_visible_case_and_a_hidden_one():
    raw = stdout_task(**{"tests/second/stdin.txt": "1\n", "tests/second/expected_stdout.txt": "1\n",
                         "hidden_tests/a/stdin.txt": None, "hidden_tests/a/expected_stdout.txt": None,
                         "hidden_tests/a/files/numbers.txt": None, "hidden_tests/b/stdin.txt": None,
                         "hidden_tests/b/expected_stdout.txt": None})
    assert_problem(raw, "exactly one visible test", "at least one hidden test")


def test_stdout_case_needs_expected_output():
    assert_problem(stdout_task(**{"hidden_tests/b/expected_stdout.txt": None}),
                   "hidden_tests/b/expected_stdout.txt: missing")


# --- zips ------------------------------------------------------------------------------


def zip_of(files: dict, prefix: str = "", symlink: str | None = None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, content in files.items():
            z.writestr(prefix + name, content)
        if symlink:
            info = zipfile.ZipInfo(prefix + symlink)
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            z.writestr(info, "/etc/passwd")
    return buf.getvalue()


def test_zip_with_a_top_level_folder():
    spec = tf.load_task_zip(zip_of(pytest_task(), prefix="revenue/"))
    assert spec.title == "Revenue per region"


def test_zip_slip_and_absolute_paths_rejected():
    for evil in ("../evil.py", "starter/../../evil.py", "/etc/evil"):
        with pytest.raises(TaskFormatError) as e:
            tf.load_task_zip(zip_of({**pytest_task(), evil: b"x"}))
        assert any("not a plain relative path" in p for p in e.value.problems), (evil, e.value.problems)


def test_zip_symlink_rejected():
    with pytest.raises(TaskFormatError) as e:
        tf.load_task_zip(zip_of(pytest_task(), symlink="data/link.csv"))
    assert any("symbolic links" in p for p in e.value.problems)


def test_zip_size_limits_checked_before_reading(monkeypatch):
    monkeypatch.setattr(tf, "MAX_DATA_FILE_BYTES", 10)
    with pytest.raises(TaskFormatError) as e:
        tf.load_task_zip(zip_of(pytest_task()))
    assert any("more than the 10 a file may have" in p for p in e.value.problems)


def test_not_a_zip():
    with pytest.raises(TaskFormatError, match="isn't a zip file"):
        tf.load_task_zip(b"hello")


def test_directory_loader(tmp_path):
    for rel, content in pytest_task().items():
        path = tmp_path / "revenue" / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    os.symlink("/etc/passwd", tmp_path / "revenue" / "data" / "link.csv")
    with pytest.raises(TaskFormatError, match="symbolic links"):
        tf.load_task_dir(str(tmp_path / "revenue"))
    os.remove(tmp_path / "revenue" / "data" / "link.csv")
    assert tf.load_task_dir(str(tmp_path / "revenue")).id == "revenue"


# --- round trip ----------------------------------------------------------------------------


@pytest.mark.parametrize("make", [pytest_task, stdout_task])
def test_export_then_import_is_identical(make):
    spec = tf.parse_task(make(), default_id="t")
    again = tf.load_task_zip(tf.to_zip(spec))
    assert again == spec


# --- BEGIN/END markers ----------------------------------------------------------------------

MARKERS = {"begin": "// BEGIN TASK", "end": "// END TASK"}
CPP = "#include <vector>\nint helper() { return 1; }\n// BEGIN TASK\nint solve() {\n  return 0;\n}\n// END TASK\nint main() {}\n"


def test_markers_validated_in_starter_and_reference():
    yaml_text = TASK_YAML + 'markers: {begin: "# BEGIN", end: "# END"}\n'
    raw = pytest_task(**{"task.yaml": yaml_text,
                        "starter/solution.py": "# BEGIN\npass\n# END\n",
                        "reference/solution.py": "# END\nx = 1\n# BEGIN\n"})
    assert_problem(raw, '"# END" comes before "# BEGIN"')
    raw = pytest_task(**{"task.yaml": yaml_text, "starter/solution.py": "pass\n"})
    assert_problem(raw, 'starter/solution.py: needs exactly one "# BEGIN" and one "# END" line (found 0 and 0)')


def test_splice_keeps_everything_outside_the_markers():
    student = CPP.replace("return 0;", "return 42;").replace("return 1;", "return 999;").replace("int main() {}", "")
    spliced = tf.splice_region(CPP, student, MARKERS)
    assert "return 42;" in spliced
    assert "return 1;" in spliced and "return 999;" not in spliced
    assert spliced.endswith("// END TASK\nint main() {}\n")


def test_splice_refuses_missing_markers():
    with pytest.raises(ValueError, match="missing or changed"):
        tf.splice_region(CPP, CPP.replace("// END TASK\n", ""), MARKERS)


def test_editable_region():
    assert tf.editable_region(CPP, MARKERS) == "int solve() {\n  return 0;\n}\n"
    assert tf.editable_region("// BEGIN TASK\n// END TASK\n", MARKERS) == ""
