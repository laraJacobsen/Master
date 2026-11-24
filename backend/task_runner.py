"""Test-graded tasks: run a task's tests against a student's files and report each test.

    run_tests(task, files, include_hidden=True) -> [TestResult]

`task` is a question row with grading_mode "tests" (task_files, task_meta, limits);
`files` is {path: content} of the student's editable files. One TestResult per test,
visible tests first, in the order the reference run found them (task_meta["test_ids"],
recorded when the task is validated). A run that crashed before reporting a test
still yields a TestResult for it (outcome "error"), so every submission of one task
has the same list of tests -- which is what the clustering's failing-test signature
needs.

Today's only runner is Judge0PytestRunner: one Judge0 submission per run (the
"Multi-file program" language with our own run script) on the judge0-pytest image
(runner/judge0-python/), running pytest with --junitxml over the student's files, the
starter's read-only files, data/, tests/ and hidden_tests/. Same CPU/memory limits as
stdout tasks (the task's own, capped by judge0_client), no network, plus
pytest-timeout per test. The CPU limit covers the whole pytest run, not each test.

Where a Java/Maven (or C++) runner plugs in: write another class with the same
run_tests(task, files, include_hidden) method and pick it in _runner_for() by
task["language"]. A Docker-based runner (docker run --network none --memory --cpus
--read-only on an image with a JDK, Maven and a pre-filled ~/.m2 holding JUnit 5, then
`mvn -o -q test` and the surefire XML in target/surefire-reports/) can reuse
parse_junit_xml() unchanged: surefire writes the same JUnit XML schema. Judge0's
isolate is a poor fit for Maven (JVM memory and process limits, JDK 13, no .m2 cache),
which is why that runner would sit outside Judge0. Everything downstream (verdict,
hints, clustering, what students see) only reads TestResult.

What the sandbox does NOT protect against: the student's code runs in the same
process as the tests, so it can read hidden_tests/, patch pytest, or write its own
report. The report sits behind a random per-run marker, and only the test ids the
reference run produced are accepted, but this is a classroom tool, not an exam
proctor (README: "not a hostile sandbox").
"""

from __future__ import annotations

import logging
import re
import secrets
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from backend import judge0_client
from backend.task_format import splice_region

logger = logging.getLogger(__name__)

PYTHON = "/usr/local/python-3.11/bin/python3.11"
VISIBLE_DIR, HIDDEN_DIR = "tests", "hidden_tests"
_MAX_REPORT_CHARS = 1_000_000
_MESSAGE_CHARS = 300
_DETAILS_CHARS = 2000
# Exit codes of `pytest`: 0 all passed, 1 some failed -- a report exists either way.
_PYTEST_RAN = (0, 1)


@dataclass
class TestResult:
    id: str  # "tests/test_sales.py::test_revenue_column" (class tests: file::Class::name)
    name: str  # "test_revenue_column"
    file: str  # "tests/test_sales.py"
    visibility: str  # "visible" | "hidden"
    outcome: str  # "passed" | "failed" | "error" | "skipped"
    message: str = ""  # one short line: "assert 0 == 42.0", "KeyError: 'revenue'"
    details: str = ""  # pytest's short traceback (lecturer only)
    error_type: str | None = None  # "AssertionError", "KeyError", "Timeout", "SyntaxError"...
    time_s: float | None = None
    # How the whole run ended in Judge0 (same for every test of one run).
    run_status: str | None = None
    run_exit_code: int | None = None

    @property
    def passed(self) -> bool:
        # A test the task's author skips must not fail anyone.
        return self.outcome in ("passed", "skipped")

    def to_result_dict(self, index: int) -> dict:
        """The per-test dict every stdout-graded result already is (judge0_client.
        run_test_cases), so hints.classify_submission(), ai_feedback and the stored
        raw_test_results read it unchanged. The crash classes come from what classify.py
        would see if this test's failure had been a program's own crash:
          - assertion failed (or pytest.fail) -> no crash, so wrong_answer
          - per-test timeout or the whole run killed for time -> timeout
          - any other exception -> a Python traceback ending in that exception, so
            runtime_error/<name>, syntax_error, oom (MemoryError), ImportError...
        """
        status, stderr, exit_code = "Accepted", "", 0
        if not self.passed:
            if self.error_type == "Timeout":
                status = "Time Limit Exceeded"
            elif self.error_type in ("AssertionError", "Failed"):
                status = "Wrong Answer"
            else:
                status = "Runtime Error (NZEC)"
                exit_code = self.run_exit_code if self.run_exit_code not in (None, 0) else 1
                last = f"{self.error_type}: {self.message.split(': ', 1)[-1]}" if self.error_type else self.message
                stderr = f"{self.details.rstrip()}\n{last}".strip()
        return {
            "case_index": index,
            "test_id": self.id,
            "test_name": self.name,
            "test_file": self.file,
            "visibility": self.visibility,
            "outcome": self.outcome,
            "message": self.message,
            "details": self.details,
            "error_type": self.error_type,
            "passed": self.passed,
            "status_id": None,
            "status_description": status,
            "stdin": "",
            "stdout": "",
            "expected_stdout": None,
            "stderr": stderr,
            "exit_code": exit_code,
            "time_s": self.time_s,
            "run_status": self.run_status,
        }


# --- JUnit XML ------------------------------------------------------------------------------

_EXC_LINE = re.compile(r"^E\s+(?:[\w.]+\.)?([A-Z]\w*(?:Error|Exception|Exit|Interrupt|Warning))\b(?::\s*(.*))?$")
_MESSAGE_TYPE = re.compile(r"^(?:[\w.]+\.)?([A-Z]\w*(?:Error|Exception|Exit|Interrupt|Warning)|Failed)(?::|$)")


def _short(text: str, n: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 3] + "..."


def _error_type(message: str, details: str) -> str | None:
    """The exception a failing test ended with, from pytest's message attribute
    ("KeyError: 'x'", "assert 1 == 2", "Failed: Timeout >2.0s") or, for collection and
    setup errors, the last `E   SomeError: ...` line of its traceback."""
    first = (message or "").strip().splitlines()[0] if (message or "").strip() else ""
    if first.startswith("Failed: Timeout"):
        return "Timeout"
    if first.startswith("assert ") or first == "assert":
        return "AssertionError"
    m = _MESSAGE_TYPE.match(first)
    if m:
        return m.group(1)
    for line in reversed((details or "").splitlines()):
        m = _EXC_LINE.match(line.strip())
        if m:
            return m.group(1)
    if "Timeout >" in (details or ""):
        return "Timeout"
    return None


def _message_for(message: str, details: str, error_type: str | None) -> str:
    first = (message or "").strip().splitlines()[0] if (message or "").strip() else ""
    if first in ("", "collection failure") or first.startswith("failed on setup") or first.startswith("failed on teardown"):
        for line in reversed((details or "").splitlines()):
            m = _EXC_LINE.match(line.strip())
            if m:
                return _short(f"{m.group(1)}: {m.group(2)}" if m.group(2) else m.group(1), _MESSAGE_CHARS)
    if first.startswith("AssertionError: assert"):  # students know the assert, not the class
        first = first[len("AssertionError: "):]
    return _short(first or (error_type or ""), _MESSAGE_CHARS)


def _visibility(path: str) -> str:
    return "hidden" if path.startswith(HIDDEN_DIR + "/") else "visible"


def parse_junit_xml(xml_text: str) -> tuple[list[TestResult], dict[str, TestResult]]:
    """pytest's --junitxml report (junit_family=xunit1, which carries each test's file)
    -> (one TestResult per test case, {test file: collection error}). Maven surefire
    reports use the same elements, so a JUnit runner can reuse this."""
    root = ET.fromstring(xml_text)
    results, collection_errors = [], {}
    for case in root.iter("testcase"):
        name = case.get("name", "")
        classname = case.get("classname", "")
        path = case.get("file") or ""
        failure = case.find("failure")
        error = case.find("error")
        skipped = case.find("skipped")
        problem = failure if failure is not None else error
        message = problem.get("message", "") if problem is not None else ""
        details = (problem.text or "") if problem is not None else ""

        if not classname and error is not None:
            # A module that failed to import:
            # <testcase classname="" name="tests.test_x" file="tests/test_x.py"><error message="collection failure">
            module_file = path or name.replace(".", "/") + ".py"
            et = _error_type(message, details)
            collection_errors[module_file] = TestResult(
                id=module_file, name=module_file, file=module_file, visibility=_visibility(module_file),
                outcome="error", message=_message_for(message, details, et), details=_short(details, _DETAILS_CHARS),
                error_type=et,
            )
            continue

        if not path:  # xunit2 has no file attribute: rebuild it from the dotted classname,
            # whose trailing CapitalizedParts are test classes (tests.test_x.TestThing).
            parts = classname.split(".")
            while len(parts) > 1 and parts[-1][:1].isupper():
                parts.pop()
            path = "/".join(parts) + ".py"
        module = path[:-3].replace("/", ".") if path.endswith(".py") else path
        cls = classname[len(module) + 1:] if classname.startswith(module + ".") else ""
        test_id = f"{path}::{cls}::{name}" if cls else f"{path}::{name}"

        if problem is not None:
            et = _error_type(message, details)
            outcome = "failed" if failure is not None else "error"
            msg = _message_for(message, details, et)
        elif skipped is not None:
            et, outcome, msg = None, "skipped", _short(skipped.get("message", ""), _MESSAGE_CHARS)
            details = ""
        else:
            et, outcome, msg, details = None, "passed", "", ""
        try:
            time_s = float(case.get("time")) if case.get("time") else None
        except ValueError:
            time_s = None
        results.append(TestResult(
            id=test_id, name=name, file=path, visibility=_visibility(path), outcome=outcome,
            message=msg, details=_short(details, _DETAILS_CHARS), error_type=et, time_s=time_s,
        ))
    return results, collection_errors


# --- assembling a run ---------------------------------------------------------------------


def _run_level_failure(run: dict, stderr_tail: str) -> tuple[str, str, str | None]:
    """(message, details, error_type) for tests a crashed run never reported."""
    status = (run.get("status_description") or "").lower()
    exit_code = run.get("exit_code")
    if "time limit" in status:
        return "Timeout: the test run took longer than the task's time limit.", "", "Timeout"
    if exit_code == 137 or "MemoryError" in stderr_tail:
        return "MemoryError: the test run used more memory than the task allows.", stderr_tail, "MemoryError"
    detail = stderr_tail or run.get("message") or run.get("status_description") or ""
    et = _error_type("", "\n".join("E   " + ln for ln in detail.splitlines()))
    return _short(f"The test run stopped before this test ({run.get('status_description')}).", _MESSAGE_CHARS), \
        _short(detail, _DETAILS_CHARS), et


def assemble(report_xml: str | None, run: dict, stderr_tail: str, expected: list[dict] | None,
             include_hidden: bool = True) -> list[TestResult]:
    """One run's TestResults, in the expected order (task_meta["test_ids"], from the
    reference run) when known, else in report order. Expected tests the report lacks
    get the collection error of their file, or the run's own failure."""
    reported, collection_errors = [], {}
    if report_xml:
        try:
            reported, collection_errors = parse_junit_xml(report_xml)
        except ET.ParseError as e:
            logger.warning("unreadable junit report: %s", e)
    status, exit_code = run.get("status_description"), run.get("exit_code")

    if expected is None:
        out = reported + list(collection_errors.values())
        if not out:
            message, details, et = _run_level_failure(run, stderr_tail)
            out = [TestResult(id="(test run)", name="(test run)", file="", visibility="visible", outcome="error",
                              message=message, details=details, error_type=et)]
    else:
        by_id = {r.id: r for r in reported}
        out = []
        for exp in expected:
            if not include_hidden and exp["visibility"] == "hidden":
                continue
            r = by_id.get(exp["id"])
            if r is None:
                coll = collection_errors.get(exp["id"].split("::", 1)[0])
                if coll is not None:
                    r = TestResult(id=exp["id"], name=exp["id"].rsplit("::", 1)[-1], file=coll.file,
                                   visibility=exp["visibility"], outcome="error", message=coll.message,
                                   details=coll.details, error_type=coll.error_type)
                else:
                    message, details, et = _run_level_failure(run, stderr_tail)
                    path = exp["id"].split("::", 1)[0]
                    r = TestResult(id=exp["id"], name=exp["id"].rsplit("::", 1)[-1], file=path,
                                   visibility=exp["visibility"], outcome="error", message=message,
                                   details=details, error_type=et)
            out.append(r)
        extra = [r.id for r in reported if r.id not in {e["id"] for e in expected}]
        if extra:
            logger.warning("test run reported tests the reference run didn't: %s", extra[:5])
    for r in out:
        r.run_status, r.run_exit_code = status, exit_code
    visible = [r for r in out if r.visibility == "visible"]
    return visible + [r for r in out if r.visibility == "hidden"]


def results_from_run(run: dict, marker: str, expected: list[dict] | None,
                     include_hidden: bool = True) -> list[TestResult]:
    """A Judge0 run of the run script -> TestResults. Its stdout is: [newline] marker,
    the JUnit report (empty if pytest never wrote one), marker, the tail of pytest's
    own output. Only text between the run's own random markers counts as the report."""
    stdout = run.get("stdout") or ""
    parts = stdout.split(f"\n{marker}\n")
    report_xml = parts[1].strip() if len(parts) >= 3 else None
    log_tail = parts[2] if len(parts) >= 3 else stdout[-4000:]
    stderr_tail = "\n".join(filter(None, [log_tail.strip(), (run.get("stderr") or "").strip()]))[-4000:]
    if report_xml and len(report_xml) > _MAX_REPORT_CHARS:
        report_xml = None
    return assemble(report_xml or None, run, stderr_tail, expected, include_hidden)


# --- the student's files in the sandbox ----------------------------------------------------


class SubmissionFilesError(ValueError):
    """The submitted files can't be graded as they are (unknown or missing file, markers removed)."""


def editable_files(task: dict) -> list[str]:
    return list((task.get("task_meta") or {}).get("editable") or [])


def starter_files(task: dict) -> dict[str, str]:
    return {f["path"]: f["content"] for f in task.get("task_files") or [] if f["role"] == "starter"}


def reference_files(task: dict) -> dict[str, str]:
    return {f["path"]: f["content"] for f in task.get("task_files") or [] if f["role"] == "reference"}


def prepare_submission(task: dict, files: dict[str, str]) -> dict[str, str]:
    """The editable files that will be graded: only files the task lets students edit,
    each one present (a missing one is taken from the starter), and in BEGIN/END marker
    mode the student's region spliced into the starter file, so edits outside the
    markers are dropped. Raises SubmissionFilesError with a student-facing message."""
    editable = editable_files(task)
    starter = starter_files(task)
    unknown = sorted(set(files) - set(editable))
    if unknown:
        raise SubmissionFilesError(f"{', '.join(unknown)} isn't a file you can edit in this task.")
    out = {}
    markers = (task.get("task_meta") or {}).get("markers")
    for path in editable:
        content = files.get(path, starter.get(path, ""))
        if markers and path in starter and path in files:
            try:
                content = splice_region(starter[path], content, markers)
            except ValueError as e:
                raise SubmissionFilesError(f"{path}: {e}")
        out[path] = content
    return out


def sandbox_files(task: dict, student_files: dict[str, str], include_hidden: bool) -> dict[str, str]:
    files = {}
    editable = set(editable_files(task))
    for f in task.get("task_files") or []:
        role, path = f["role"], f["path"]
        if role == "starter" and path not in editable:
            files[path] = f["content"]
        elif role == "data":
            files[f"data/{path}"] = f["content"]
        elif role == "test":
            files[f"{VISIBLE_DIR}/{path}"] = f["content"]
        elif role == "hidden_test" and include_hidden:
            files[f"{HIDDEN_DIR}/{path}"] = f["content"]
    files.update(student_files)
    return files


# --- runners --------------------------------------------------------------------------------


class Judge0PytestRunner:
    """pytest inside Judge0 (isolate), on the judge0-pytest image's Python 3.11."""

    def run_tests(self, task: dict, files: dict[str, str], include_hidden: bool = True) -> list[TestResult]:
        meta = task.get("task_meta") or {}
        token = secrets.token_hex(12)
        report, log = f".report-{token}.xml", f".pytest-{token}.log"
        marker = f"@@REPORT-{token}@@"
        targets = [VISIBLE_DIR] + ([HIDDEN_DIR] if include_hidden and any(
            f["role"] == "hidden_test" for f in task.get("task_files") or []) else [])
        test_timeout = float(meta.get("test_timeout_s") or 2)
        run_script = (
            "#!/bin/bash\n"
            # One thread per numeric library: isolate caps processes/threads, and a
            # classroom exercise gains nothing from BLAS threads.
            "export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1\n"
            "export PYTHONDONTWRITEBYTECODE=1 PYTHONHASHSEED=0 MPLBACKEND=Agg\n"
            f"{PYTHON} -m pytest -q -p no:cacheprovider --rootdir=. --tb=short -o junit_family=xunit1 "
            f"--timeout={test_timeout:g} --junitxml={report} {' '.join(targets)} > {log} 2>&1\n"
            "status=$?\n"
            f"printf '\\n%s\\n' '{marker}'\n"
            f"cat {report} 2>/dev/null\n"
            f"printf '\\n%s\\n' '{marker}'\n"
            f"tail -c 4000 {log}\n"
            # pytest ran (all passed or some failed): the run itself succeeded.
            f"case $status in 0|1) exit 0;; *) exit $status;; esac\n"
        )
        cpu = task.get("cpu_time_limit_s")
        run = judge0_client.run_archive(
            sandbox_files(task, files, include_hidden),
            run_script,
            cpu_time_limit=cpu,
            memory_limit_kb=task.get("memory_limit_kb"),
            wall_time_limit=min(20.0, 2 * float(cpu or judge0_client.DEFAULT_CPU_TIME_LIMIT) + 2),
        )
        results = results_from_run(run, marker, meta.get("test_ids"), include_hidden)
        logger.info("pytest run: %s, cpu %ss, %s KB, %d tests, %d passed", run.get("status_description"),
                    run.get("time_s"), run.get("memory_kb"), len(results), sum(r.passed for r in results))
        return results


def _runner_for(task: dict):
    if task.get("language") == "python":
        return Judge0PytestRunner()
    # Java/Maven and C++ runners go here (see the module docstring).
    raise NotImplementedError(f"No test runner for {task.get('language')!r} tasks yet.")


def run_tests(task: dict, files: dict[str, str], include_hidden: bool = True) -> list[TestResult]:
    """Run the task's tests (visible, plus hidden unless include_hidden=False) against
    `files`, the student's editable files after prepare_submission(). Raises
    judge0_client.Judge0Error when Judge0 itself can't be reached."""
    return _runner_for(task).run_tests(task, files, include_hidden)


def expected_test_ids(results: list[TestResult]) -> list[dict]:
    """What a reference run found, stored as task_meta["test_ids"] at validation."""
    return [{"id": r.id, "visibility": r.visibility} for r in results if "::" in r.id]


def as_dicts(results: list[TestResult]) -> list[dict]:
    return [r.to_result_dict(i) for i, r in enumerate(results)]
