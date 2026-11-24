"""Task-as-folder format: load, validate and write a task folder (or a zip of one).

    <task-id>/
      task.yaml       title, description, language, grading mode, limits, editable files...
      starter/        the files students get (may contain TODOs); several are fine
      tests/          visible tests
      hidden_tests/   tests students don't see
      reference/      the reference solution: replaces the editable starter files
      data/           data files (CSV etc.), placed at data/<name> next to the program
      wrong/          optional: typical wrong solutions, one folder each (wrong/<name>/solution.py),
                      holding only the editable files that differ from reference/. "Check
                      solution" makes sure the tests catch each one; never sent to students
      requirements.txt  optional: what the task needs from the runner image

task.yaml (only title, description and language are required):

    title: Revenue per region
    description: |
      Shown to students. Plain text.
    language: python            # python | c | java | cpp
    grading: tests              # tests (pytest) | stdout (compare printed output)
    editable: [solution.py]     # starter files students may change; the rest are read-only.
                                # Default: every starter file.
    time_limit_s: 5             # CPU time for one submission (the whole test run)
    memory_limit_mb: 128        # MiB (x 1024 KB, as the setup page counts); at most 250
    test_timeout_s: 2           # tests mode: per test (pytest-timeout)
    duration_minutes: 10        # how long the task runs in the lecture
    markers:                    # optional BEGIN/END mode: students edit only between
      begin: "# BEGIN TASK"     # the markers of each editable file; everything else is
      end: "# END TASK"         # put back from the starter when the code is graded
    allowed_packages: [scipy]   # extra imports students may use (besides requirements.txt's)
    line_limit: 200             # longest submission accepted (lines, all editable files together)
    hints:                      # optional: the task's own wrong-answer hints, attempt 1 first
      - Check what happens to rows with no units.
    output_file: result.txt     # stdout grading only: grade this file instead of what's printed
    wrong_solutions:            # optional: the tests each wrong/<name>/ must fail (by test
      forgot_fillna: [test_missing_units_count_as_zero]   # name). A wrong solution not listed
                                # here must still fail at least one test.
    hidden_test_hints:          # optional: one sentence a student sees when that hidden test
      test_missing_units_count_as_zero: Checks a sale with no units recorded.   # fails. Only
                                # what's written here is shown; other hidden tests stay a count.

Grading "stdout" is the app's original model, so a task created in the setup page can
be exported and re-imported: each test is a folder with stdin.txt, expected_stdout.txt
and optional files/ (data the program opens by name). Exactly one visible test
(tests/<name>/): it's the worked example students see. The others go in
hidden_tests/<name>/, sorted by folder name.

Grading "tests" (Python only for now): tests/ and hidden_tests/ hold pytest files
(test_*.py, plus helpers such as conftest.py). In the sandbox the student's files sit at
the root, so tests import them by module name (from solution import ...) and open data
files as data/<name>.

Nothing in requirements.txt is installed when a task runs (the sandbox has no network):
each line must already be satisfied by the runner image's pins
(runner/judge0-python/versions.env), so a task that needs something else fails here,
with a clear message, instead of with an ImportError in front of the class.

Loading never raises on the first problem: TaskFormatError carries every problem found,
each starting with the path it's about.
"""

from __future__ import annotations

import ast
import io
import os
import posixpath
import re
import zipfile
from dataclasses import dataclass, field

import yaml
from packaging.requirements import InvalidRequirement, Requirement

# --- limits ----------------------------------------------------------------------------

MAX_FILES = 200
MAX_CODE_FILE_BYTES = 1_000_000  # starter/tests/reference: the same 1 MB as a test case's files
MAX_DATA_FILE_BYTES = 5_000_000
# Judge0 refuses an additional_files zip that unpacks to more than max_extract_size
# (10240 KB on our instance); keep a margin for the student's code and the run script.
MAX_TOTAL_BYTES = 8_000_000
MAX_ZIP_BYTES = 20_000_000  # the upload itself

LANGUAGES = ("python", "c", "java", "cpp")
GRADING_MODES = ("stdout", "tests")
# What each grading mode can run today. Java tests need a Maven/JUnit runner (see
# backend/task_runner.py); C++ isn't a Judge0 language in judge0_client yet.
SUPPORTED = {"stdout": ("python", "c", "java"), "tests": ("python",)}

ROLES = ("starter", "test", "hidden_test", "reference", "data", "wrong")
_ROLE_DIRS = {"starter": "starter", "test": "tests", "hidden_test": "hidden_tests",
              "reference": "reference", "data": "data", "wrong": "wrong"}
_DIR_ROLES = {v: k for k, v in _ROLE_DIRS.items()}

# Letters, digits, ".", "-", "_" per part, "/" between parts; no hidden files, no "..".
_PART_RE = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9_.-]*$")
# Names the test runner itself writes next to the program (see backend/task_runner.py).
RESERVED_ROOT_NAMES = {"run", "compile", "report.xml", "_classloop_collect.py"}
# Junk a zip made on macOS/Windows or a used folder tends to carry: skipped, not errors.
_IGNORED_PARTS = {"__MACOSX", "__pycache__", ".DS_Store", ".pytest_cache", "Thumbs.db", ".git"}

_KNOWN_KEYS = {
    "id", "title", "description", "language", "grading", "editable", "time_limit_s",
    "memory_limit_mb", "test_timeout_s", "duration_minutes", "markers", "allowed_packages",
    "line_limit", "hints", "output_file", "wrong_solutions", "hidden_test_hints",
}

VERSIONS_ENV = os.path.join(os.path.dirname(__file__), "..", "runner", "judge0-python", "versions.env")


class TaskFormatError(ValueError):
    """Every problem found in one task folder, each a line starting with its path."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("This task folder can't be used:\n" + "\n".join(f"- {p}" for p in problems))


@dataclass
class TaskFile:
    path: str  # relative to its role's folder, e.g. "solution.py" or "sales.csv"
    role: str  # one of ROLES
    content: str

    @property
    def sandbox_path(self) -> str:
        """Where the file sits next to the program when it runs."""
        if self.role in ("starter", "reference"):
            return self.path
        return f"{_ROLE_DIRS[self.role]}/{self.path}"


@dataclass
class StdoutCase:
    name: str
    stdin: str
    expected_stdout: str
    files: list = field(default_factory=list)  # [{"name", "content"}], like the app's test cases
    visible: bool = False


@dataclass
class TaskSpec:
    id: str
    title: str
    description: str
    language: str
    grading: str
    editable: list[str]
    cpu_time_limit_s: float = 5
    memory_limit_kb: int = 128000
    test_timeout_s: float = 2
    duration_seconds: int = 600
    markers: dict | None = None  # {"begin", "end"}
    line_limit: int = 200
    hints: list[str] = field(default_factory=list)
    output_file: str | None = None
    # wrong/<name>/ -> the test names it must fail ([] = at least one, any).
    wrong_solutions: dict[str, list[str]] = field(default_factory=dict)
    # hidden test name -> the sentence students see when it fails.
    hidden_test_hints: dict[str, str] = field(default_factory=dict)
    requirements: list[str] = field(default_factory=list)
    allowed_packages: list[str] = field(default_factory=list)
    files: list[TaskFile] = field(default_factory=list)
    stdout_cases: list[StdoutCase] = field(default_factory=list)

    def files_with_role(self, role: str) -> list[TaskFile]:
        return [f for f in self.files if f.role == role]

    @property
    def extra_packages(self) -> list[str]:
        """Imports students may use beyond the standard library: requirements.txt's
        packages plus allowed_packages (backend/validation.py's allow-list)."""
        names = [Requirement(r).name for r in self.requirements] + self.allowed_packages
        return sorted({n.lower() for n in names} - {"pytest", "pytest-timeout"})


# --- runner image pins -------------------------------------------------------------------


def image_pins(path: str = VERSIONS_ENV) -> dict[str, str]:
    """{package: version} for every <NAME>_VERSION in versions.env except Python's:
    PANDAS_VERSION=2.2.3 -> {"pandas": "2.2.3"}, PYTEST_TIMEOUT_VERSION -> "pytest-timeout"."""
    pins = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.endswith("_VERSION") and key != "PYTHON_VERSION":
                pins[key[: -len("_VERSION")].lower().replace("_", "-")] = value.strip()
    return pins


def check_requirements(lines: list[str], pins: dict[str, str]) -> list[str]:
    """Problems with requirements.txt lines against the image's pins (empty: all fine)."""
    problems = []
    for line in lines:
        try:
            req = Requirement(line)
        except InvalidRequirement:
            problems.append(f'requirements.txt: "{line}" isn\'t a requirement line (e.g. pandas==2.2.3).')
            continue
        name = req.name.lower().replace("_", "-")
        if name not in pins:
            problems.append(
                f'requirements.txt: "{req.name}" isn\'t in the runner image (it has '
                f'{", ".join(f"{k} {v}" for k, v in sorted(pins.items()))}); nothing is installed '
                f'at run time. Add it to runner/judge0-python/versions.env and rebuild the image.'
            )
        elif req.specifier and not req.specifier.contains(pins[name], prereleases=True):
            problems.append(
                f'requirements.txt: "{line}" doesn\'t match the runner image\'s {name} {pins[name]}. '
                f'Change the pin in runner/judge0-python/versions.env and rebuild, or relax the requirement.'
            )
    return problems


# --- reading -----------------------------------------------------------------------------


def _ignored(rel: str) -> bool:
    parts = rel.split("/")
    return any(p in _IGNORED_PARTS for p in parts) or rel.endswith(".pyc")


def _check_path(rel: str) -> str | None:
    parts = rel.split("/")
    if rel.startswith("/") or any(p in ("", ".", "..") for p in parts) or "\\" in rel:
        return f"{rel}: not a plain relative path."
    if any(not _PART_RE.match(p) for p in parts):
        return (f'{rel}: use only letters, digits, ".", "-" and "_" in file and folder names '
                f'(no spaces, no names starting with "." or "-").')
    if len(rel) > 200:
        return f"{rel}: path too long (max 200 characters)."
    return None


def read_dir(path: str) -> dict[str, bytes]:
    """Every file under `path` as {relative posix path: bytes}. Symlinks are refused
    (a task folder is copied into the database, not linked to)."""
    if not os.path.isdir(path):
        raise TaskFormatError([f"{path}: not a folder."])
    files, problems = {}, []
    for root, dirs, names in os.walk(path):
        dirs[:] = sorted(d for d in dirs if d not in _IGNORED_PARTS)
        for name in sorted(names):
            full = os.path.join(root, name)
            rel = os.path.relpath(full, path).replace(os.sep, "/")
            if _ignored(rel):
                continue
            if os.path.islink(full):
                problems.append(f"{rel}: symbolic links aren't allowed; copy the file in.")
                continue
            if len(files) >= MAX_FILES:
                problems.append(f"The folder has more than {MAX_FILES} files.")
                break
            size = os.path.getsize(full)
            if size > MAX_DATA_FILE_BYTES:
                problems.append(f"{rel}: {size:,} bytes, more than the {MAX_DATA_FILE_BYTES:,} a file may have.")
                continue
            with open(full, "rb") as f:
                files[rel] = f.read()
    if problems:
        raise TaskFormatError(problems)
    return files


def read_zip(data: bytes) -> dict[str, bytes]:
    """A zip of a task folder as {relative posix path: bytes}. task.yaml may sit at the
    zip's root or inside one top-level folder (what zipping a folder gives). Refuses
    absolute or ../ paths, symlinks, and anything over the size limits before reading
    it (sizes come from the zip's directory, and each read is capped again)."""
    if len(data) > MAX_ZIP_BYTES:
        raise TaskFormatError([f"The zip is {len(data):,} bytes; the limit is {MAX_ZIP_BYTES:,}."])
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise TaskFormatError(["The upload isn't a zip file."])

    entries = [i for i in zf.infolist() if not i.is_dir() and not _ignored(i.filename)]
    problems = []
    if len(entries) > MAX_FILES:
        raise TaskFormatError([f"The zip has {len(entries)} files; a task may have at most {MAX_FILES}."])

    names = [i.filename for i in entries]
    prefix = ""
    if "task.yaml" not in names:
        tops = {n.split("/", 1)[0] for n in names}
        if len(tops) == 1 and f"{next(iter(tops))}/task.yaml" in names:
            prefix = next(iter(tops)) + "/"

    files, total = {}, 0
    for info in entries:
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            problems.append(f"{info.filename}: symbolic links aren't allowed.")
            continue
        if not info.filename.startswith(prefix):
            problems.append(f"{info.filename}: outside the task folder {prefix.rstrip('/')}.")
            continue
        rel = info.filename[len(prefix):]
        bad = _check_path(rel)
        if bad:
            problems.append(bad)
            continue
        if info.file_size > MAX_DATA_FILE_BYTES:
            problems.append(f"{rel}: {info.file_size:,} bytes, more than the {MAX_DATA_FILE_BYTES:,} a file may have.")
            continue
        total += info.file_size
        if total > MAX_TOTAL_BYTES:
            problems.append(f"The task's files add up to more than {MAX_TOTAL_BYTES:,} bytes.")
            break
        with zf.open(info) as f:
            content = f.read(MAX_DATA_FILE_BYTES + 1)
        if len(content) > MAX_DATA_FILE_BYTES:  # the directory lied about the size
            problems.append(f"{rel}: larger than its zip entry says.")
            continue
        files[rel] = content
    if problems:
        raise TaskFormatError(problems)
    return files


def load_task_dir(path: str) -> TaskSpec:
    return parse_task(read_dir(path), default_id=os.path.basename(os.path.normpath(path)))


def load_task_zip(data: bytes, default_id: str = "task") -> TaskSpec:
    """Without an id in task.yaml, the task's id is the folder name inside the zip when
    there is one (a zipped folder), else default_id (the upload's file name). The folder
    name is the stable one: a browser saves a second download as "task (1).zip", and the
    id is what makes a re-import replace the earlier draft."""
    folder = _zip_folder_name(data)
    if folder and re.match(r"^[a-z0-9][a-z0-9-]*$", folder):
        default_id = folder
    return parse_task(read_zip(data), default_id=default_id)


def _zip_folder_name(data: bytes) -> str | None:
    try:
        names = [i.filename for i in zipfile.ZipFile(io.BytesIO(data)).infolist()
                 if not i.is_dir() and not _ignored(i.filename)]
    except zipfile.BadZipFile:
        return None
    if "task.yaml" in names:
        return None
    tops = {n.split("/", 1)[0] for n in names}
    return next(iter(tops)) if len(tops) == 1 else None


# --- validation ----------------------------------------------------------------------------


def _number(meta, key, default, problems, lo, hi):
    value = meta.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not lo <= value <= hi:
        problems.append(f"task.yaml: {key} must be a number from {lo} to {hi} (got {value!r}).")
        return default
    return value


def _string_list(meta, key, problems) -> list[str]:
    value = meta.get(key, [])
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(v, str) and v.strip() for v in value):
        problems.append(f"task.yaml: {key} must be a list of names, e.g. [solution.py].")
        return []
    return [v.strip() for v in value]


def _pytest_test_names(source: str) -> list[str]:
    """test_* functions at module level or in Test* classes (what pytest collects by default)."""
    tree = ast.parse(source)
    names = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test"):
            names.append(node.name)
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            names += [n.name for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                      and n.name.startswith("test")]
    return names


def _count_pytest_tests(source: str) -> int:
    return len(_pytest_test_names(source))


MAX_HIDDEN_HINT_CHARS = 200


def _check_hidden_test_hints(spec: TaskSpec, meta: dict, problems: list[str]) -> None:
    """task.yaml's hidden_test_hints: {hidden test name: one sentence}."""
    hints = meta.get("hidden_test_hints")
    if hints is None:
        return
    if not isinstance(hints, dict) or not all(isinstance(k, str) and isinstance(v, str) and v.strip()
                                              for k, v in hints.items()):
        problems.append("task.yaml: hidden_test_hints maps a hidden test's name to one sentence, e.g. "
                        "hidden_test_hints: {test_missing_units_count_as_zero: Checks a sale with no units.}")
        return
    hidden_names = set()
    for f in spec.files_with_role("hidden_test"):
        if posixpath.basename(f.path).startswith("test_") and f.path.endswith(".py"):
            try:
                hidden_names.update(_pytest_test_names(f.content))
            except SyntaxError:
                pass
    for name, text in hints.items():
        if name not in hidden_names:
            problems.append(f"task.yaml: hidden_test_hints lists {name}, which isn't a test in hidden_tests/.")
        elif len(text.strip()) > MAX_HIDDEN_HINT_CHARS:
            problems.append(f"task.yaml: hidden_test_hints.{name} is longer than {MAX_HIDDEN_HINT_CHARS} "
                            f"characters; keep it to one sentence.")
    spec.hidden_test_hints = {k: v.strip() for k, v in sorted(hints.items())}


def _check_wrong_solutions(spec: TaskSpec, meta: dict, problems: list[str]) -> None:
    """wrong/<name>/<editable file> folders and task.yaml's wrong_solutions."""
    variants: dict[str, set[str]] = {}
    for f in spec.files_with_role("wrong"):
        name, _, path = f.path.partition("/")
        if not path:
            problems.append(f"wrong/{f.path}: each wrong solution is a folder (wrong/<name>/solution.py).")
            continue
        if path not in spec.editable:
            problems.append(f"wrong/{f.path}: not an editable file ({', '.join(spec.editable)}). A wrong solution "
                            f"holds only the editable files that differ from reference/.")
        variants.setdefault(name, set()).add(path)
    if variants and spec.grading != "tests":
        problems.append("wrong/: wrong solutions are only checked for grading: tests.")

    listed = meta.get("wrong_solutions")
    if listed is None:
        listed = {}
    if not isinstance(listed, dict) or not all(
            isinstance(v, list) and all(isinstance(t, str) for t in v) or v is None for v in listed.values()):
        problems.append("task.yaml: wrong_solutions maps a wrong/ folder name to a list of test names, e.g. "
                        "wrong_solutions: {forgot_fillna: [test_missing_units_count_as_zero]}.")
        listed = {}
    test_names = set()
    for f in spec.files_with_role("test") + spec.files_with_role("hidden_test"):
        if posixpath.basename(f.path).startswith("test_") and f.path.endswith(".py"):
            try:
                test_names.update(_pytest_test_names(f.content))
            except SyntaxError:
                pass  # reported with its line number elsewhere
    for name, tests in listed.items():
        if name not in variants:
            problems.append(f"task.yaml: wrong_solutions lists {name}, but wrong/{name}/ doesn't exist.")
        for t in tests or []:
            if t not in test_names:
                problems.append(f"task.yaml: wrong_solutions.{name} lists {t}, which isn't a test in tests/ or "
                                f"hidden_tests/.")
    spec.wrong_solutions = {name: list(listed.get(name) or []) for name in sorted(variants)}


def _marker_problem(text: str, markers: dict) -> str | None:
    """None when `text` has exactly one begin marker followed by exactly one end marker."""
    begin, end = markers["begin"], markers["end"]
    nb, ne = text.count(begin), text.count(end)
    if nb != 1 or ne != 1:
        return f'needs exactly one "{begin}" and one "{end}" line (found {nb} and {ne}).'
    if text.index(begin) > text.index(end):
        return f'"{end}" comes before "{begin}".'
    return None


def parse_task(raw: dict[str, bytes], default_id: str = "task") -> TaskSpec:
    """Validate a task folder's files ({relative path: bytes}) into a TaskSpec, or raise
    TaskFormatError listing every problem."""
    problems: list[str] = []

    if "task.yaml" not in raw:
        tops = sorted({p.split("/", 1)[0] for p in raw})
        raise TaskFormatError([
            "task.yaml is missing at the top of the task folder"
            + (f" (found: {', '.join(tops[:8])})." if tops else " (the folder is empty).")
        ])

    text: dict[str, str] = {}
    for rel, content in raw.items():
        bad = _check_path(rel)
        if bad:
            problems.append(bad)
            continue
        try:
            text[rel] = content.decode("utf-8")
        except UnicodeDecodeError:
            problems.append(f"{rel}: not a UTF-8 text file. Only text files are supported for now "
                            f"(CSV yes; Excel/Parquet not yet).")
    total = sum(len(c) for c in raw.values())
    if total > MAX_TOTAL_BYTES:
        problems.append(f"The task's files add up to {total:,} bytes; the limit is {MAX_TOTAL_BYTES:,}.")

    try:
        meta = yaml.safe_load(text.get("task.yaml", "")) or {}
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f" (line {mark.line + 1})" if mark else ""
        raise TaskFormatError(problems + [f"task.yaml: not valid YAML{where}: {getattr(e, 'problem', e)}"])
    if not isinstance(meta, dict):
        raise TaskFormatError(problems + ["task.yaml: must be a mapping of keys (title: ..., language: ...)."])

    unknown = sorted(set(meta) - _KNOWN_KEYS)
    if unknown:
        problems.append(f"task.yaml: unknown key(s) {', '.join(unknown)} (known: {', '.join(sorted(_KNOWN_KEYS))}).")

    def required_text(key):
        value = meta.get(key)
        if not isinstance(value, str) or not value.strip():
            problems.append(f"task.yaml: {key} is required (text).")
            return ""
        return value.strip()

    title = required_text("title")
    description = required_text("description")
    language = meta.get("language")
    if language not in LANGUAGES:
        problems.append(f"task.yaml: language must be one of {', '.join(LANGUAGES)} (got {language!r}).")
    grading = meta.get("grading", "stdout")
    if grading not in GRADING_MODES:
        problems.append(f"task.yaml: grading must be one of {', '.join(GRADING_MODES)} (got {grading!r}).")
    elif language in LANGUAGES and language not in SUPPORTED[grading]:
        problems.append(
            f"task.yaml: grading: {grading} isn't supported for {language} yet "
            f"(supported: {', '.join(SUPPORTED[grading])})."
        )

    task_id = meta.get("id", default_id)
    if not isinstance(task_id, str) or not re.match(r"^[a-z0-9][a-z0-9-]*$", task_id or ""):
        problems.append(f"task.yaml: id must be lowercase letters, digits and '-' (got {task_id!r}).")
        task_id = "task"

    spec = TaskSpec(
        id=task_id, title=title, description=description, language=language or "python",
        grading=grading if grading in GRADING_MODES else "stdout", editable=[],
        cpu_time_limit_s=_number(meta, "time_limit_s", 5, problems, 0.5, 15),
        memory_limit_kb=round(_number(meta, "memory_limit_mb", 128, problems, 16, 250) * 1024),
        test_timeout_s=_number(meta, "test_timeout_s", 2, problems, 0.5, 15),
        duration_seconds=int(_number(meta, "duration_minutes", 10, problems, 1, 180) * 60),
        allowed_packages=_string_list(meta, "allowed_packages", problems),
        line_limit=int(_number(meta, "line_limit", 200, problems, 5, 5000)),
        hints=_string_list(meta, "hints", problems),
    )

    output_file = meta.get("output_file")
    if output_file is not None:
        if not isinstance(output_file, str) or _check_path(output_file.strip()):
            problems.append(f"task.yaml: output_file must be a plain file name like result.txt (got {output_file!r}).")
        elif grading != "stdout":
            problems.append("task.yaml: output_file only works with grading: stdout.")
        else:
            spec.output_file = output_file.strip()

    markers = meta.get("markers")
    if markers is not None:
        if (not isinstance(markers, dict) or set(markers) != {"begin", "end"}
                or not all(isinstance(markers[k], str) and markers[k].strip() for k in ("begin", "end"))
                or markers["begin"] == markers["end"]):
            problems.append('task.yaml: markers needs two different texts, e.g. '
                            'markers: {begin: "# BEGIN TASK", end: "# END TASK"}.')
        else:
            spec.markers = {"begin": markers["begin"].strip(), "end": markers["end"].strip()}

    # Sort every file into its role.
    other = []
    for rel in sorted(text):
        if rel in ("task.yaml", "requirements.txt"):
            continue
        top, _, rest = rel.partition("/")
        if top in _DIR_ROLES and rest:
            spec.files.append(TaskFile(rest, _DIR_ROLES[top], text[rel]))
        else:
            other.append(rel)
    if other:
        problems.append(
            f"{', '.join(other[:5])}: files must be inside starter/, tests/, hidden_tests/, reference/ "
            f"or data/ (or be task.yaml / requirements.txt)."
        )

    for f in spec.files:
        limit = MAX_DATA_FILE_BYTES if f.role == "data" else MAX_CODE_FILE_BYTES
        size = len(f.content.encode("utf-8"))
        if size > limit:
            problems.append(f"{_ROLE_DIRS[f.role]}/{f.path}: {size:,} bytes; the limit is {limit:,}.")

    starter = {f.path: f for f in spec.files_with_role("starter")}
    reference = {f.path: f for f in spec.files_with_role("reference")}
    # A stdout task may leave starter/ out: students then get the app's default
    # starter for the language (what a setup-page task without starter code does).
    if not starter and not (spec.grading == "stdout" and len(reference) == 1):
        problems.append("starter/: missing or empty. Put the file(s) students start from here.")
    if not reference:
        problems.append("reference/: missing or empty. Put the reference solution here.")

    if "editable" in meta:
        editable = _string_list(meta, "editable", problems)
    else:
        editable = sorted(starter) or sorted(reference)
    for path in editable:
        if starter and path not in starter:
            problems.append(f"task.yaml: editable lists {path}, but starter/{path} doesn't exist.")
    if not editable and (starter or reference):
        problems.append("task.yaml: editable is empty; students need at least one file to work in.")
    spec.editable = editable
    for path in reference:
        if path not in editable:
            problems.append(
                f"reference/{path}: not an editable file. reference/ holds the solved "
                f"version of the editable files ({', '.join(editable) or 'none'}), nothing else."
            )
    for path in editable:
        if reference and path not in reference:
            problems.append(f"reference/{path}: missing. Every editable file needs its solved version.")

    for path in starter:
        if path.split("/", 1)[0] in _ROLE_DIRS.values():
            problems.append(f"starter/{path}: would collide with the {path.split('/', 1)[0]}/ folder "
                            f"when the task runs. Rename it.")
        if path in RESERVED_ROOT_NAMES:
            problems.append(f"starter/{path}: a name the grader uses itself. Rename it.")

    if spec.markers:
        for path in editable:
            for role, files in (("starter", starter), ("reference", reference)):
                if path in files:
                    bad = _marker_problem(files[path].content, spec.markers)
                    if bad:
                        problems.append(f"{role}/{path}: {bad}")

    req_text = text.get("requirements.txt", "")
    spec.requirements = [ln.split("#", 1)[0].strip() for ln in req_text.splitlines()
                         if ln.split("#", 1)[0].strip()]
    if spec.requirements:
        if spec.language != "python":
            problems.append("requirements.txt: only Python tasks can have one.")
        else:
            problems.extend(check_requirements(spec.requirements, image_pins()))

    if spec.grading == "tests":
        _check_pytest_tests(spec, problems)
    else:
        _load_stdout_cases(spec, problems)
    _check_wrong_solutions(spec, meta, problems)
    _check_hidden_test_hints(spec, meta, problems)

    if spec.language == "python":
        for f in spec.files:
            if f.path.endswith(".py") and f.role in ("starter", "reference", "test", "hidden_test"):
                try:
                    ast.parse(f.content)
                except SyntaxError as e:
                    if not (f.role == "starter" and f.path in editable):  # a starter may be unfinished
                        problems.append(f"{_ROLE_DIRS[f.role]}/{f.path}: line {e.lineno}: {e.msg}.")

    if problems:
        raise TaskFormatError(problems)
    return spec


def _check_pytest_tests(spec: TaskSpec, problems: list[str]) -> None:
    for role in ("test", "hidden_test"):
        folder = _ROLE_DIRS[role]
        test_files = [f for f in spec.files_with_role(role)
                      if posixpath.basename(f.path).startswith("test_") and f.path.endswith(".py")]
        if role == "test" and not test_files:
            problems.append(f"{folder}/: no test files (test_*.py). Students need at least one visible test.")
        for f in test_files:
            try:
                n = _count_pytest_tests(f.content)
            except SyntaxError:
                continue  # reported below with the line number
            if n == 0:
                problems.append(f"{folder}/{f.path}: no test functions (def test_...).")
    # A file students edit is imported by pytest itself if it's a conftest or pytest
    # config, which would let them change how they're graded.
    for path in spec.editable:
        if posixpath.basename(path) in ("conftest.py", "pytest.ini", "pyproject.toml", "setup.cfg", "tox.ini"):
            problems.append(f"task.yaml: editable includes {path}, which pytest reads as configuration; "
                            f"students could change how they're graded. Make it read-only.")
    # pytest (rootdir mode, no __init__.py) can't import two test modules with the same
    # file name, so tests/test_x.py and hidden_tests/test_x.py would break collection.
    visible = {posixpath.basename(f.path) for f in spec.files_with_role("test") if f.path.endswith(".py")}
    for f in spec.files_with_role("hidden_test"):
        name = posixpath.basename(f.path)
        if f.path.endswith(".py") and name in visible and name != "conftest.py":
            problems.append(f"hidden_tests/{f.path}: same file name as a visible test; pytest can't "
                            f"import both. Rename one (e.g. test_hidden_*.py).")
    starter_modules = {posixpath.splitext(p)[0] for p in (f.path for f in spec.files_with_role("starter"))}
    for f in spec.files_with_role("test") + spec.files_with_role("hidden_test"):
        if posixpath.splitext(posixpath.basename(f.path))[0] in starter_modules:
            problems.append(f"{_ROLE_DIRS[f.role]}/{f.path}: same module name as a starter file.")


def _load_stdout_cases(spec: TaskSpec, problems: list[str]) -> None:
    """tests/<case>/ and hidden_tests/<case>/ folders -> spec.stdout_cases (visible first)."""
    for role, visible in (("test", True), ("hidden_test", False)):
        folder = _ROLE_DIRS[role]
        by_case: dict[str, dict[str, str]] = {}
        for f in spec.files_with_role(role):
            case, _, rest = f.path.partition("/")
            if not rest:
                problems.append(f"{folder}/{f.path}: with grading: stdout, each test is a folder "
                                f"({folder}/<name>/stdin.txt and expected_stdout.txt).")
                continue
            by_case.setdefault(case, {})[rest] = f.content
        for case in sorted(by_case):
            files = by_case[case]
            if "expected_stdout.txt" not in files:
                problems.append(f"{folder}/{case}/expected_stdout.txt: missing.")
                continue
            extra = [p for p in files if p not in ("stdin.txt", "expected_stdout.txt") and not p.startswith("files/")]
            if extra:
                problems.append(f"{folder}/{case}/: unexpected {', '.join(extra)} (only stdin.txt, "
                                f"expected_stdout.txt and files/...).")
            spec.stdout_cases.append(StdoutCase(
                name=case, stdin=files.get("stdin.txt", ""), expected_stdout=files["expected_stdout.txt"],
                files=[{"name": p[len("files/"):], "content": c} for p, c in sorted(files.items())
                       if p.startswith("files/")],
                visible=visible,
            ))
    n_visible = sum(1 for c in spec.stdout_cases if c.visible)
    if n_visible != 1:
        problems.append(f"tests/: grading: stdout needs exactly one visible test, the example students see "
                        f"(found {n_visible}). Put the others in hidden_tests/.")
    if not any(not c.visible for c in spec.stdout_cases):
        problems.append("hidden_tests/: grading: stdout needs at least one hidden test; the visible example "
                        "isn't graded.")
    if len(spec.editable) != 1:
        problems.append("task.yaml: grading: stdout supports exactly one editable file for now.")
    if spec.files_with_role("data"):
        problems.append("data/: grading: stdout attaches data per test (tests/<name>/files/...), not in data/.")


# --- BEGIN/END markers ---------------------------------------------------------------------


def editable_region(text: str, markers: dict) -> str | None:
    """The text between the begin and end marker lines (exclusive), or None if the
    markers aren't there exactly once and in order."""
    if _marker_problem(text, markers):
        return None
    start = text.index(markers["begin"])
    start = text.find("\n", start) + 1 if "\n" in text[start:] else len(text)
    end = text.rfind("\n", 0, text.index(markers["end"])) + 1
    return text[start:end] if end >= start else ""


def splice_region(original: str, submitted: str, markers: dict) -> str:
    """The original file with its marked region replaced by the submitted file's marked
    region: whatever the student changed outside the markers is dropped. Raises
    ValueError when the submitted file lost its markers."""
    region = editable_region(submitted, markers)
    if region is None:
        raise ValueError(f'The "{markers["begin"]}" / "{markers["end"]}" lines are missing or changed; '
                         f'put them back and edit only between them.')
    start = original.index(markers["begin"])
    start = original.find("\n", start) + 1
    end = original.rfind("\n", 0, original.index(markers["end"])) + 1
    return original[:start] + region + original[end:]


# --- writing ---------------------------------------------------------------------------------


def _mib(kb: int):
    """KB -> MiB for task.yaml: a whole number when it is one (131072 -> 128), else
    exact to the KB (128000 -> 125, 64000 -> 62.5)."""
    mib = kb / 1024
    return int(mib) if mib == int(mib) else round(mib, 4)


def task_yaml(spec: TaskSpec) -> str:
    meta = {
        "id": spec.id,
        "title": spec.title,
        "description": spec.description,
        "language": spec.language,
        "grading": spec.grading,
        "editable": spec.editable,
        "time_limit_s": spec.cpu_time_limit_s,
        "memory_limit_mb": _mib(spec.memory_limit_kb),
        "duration_minutes": max(1, round(spec.duration_seconds / 60)),
    }
    if spec.grading == "tests":
        meta["test_timeout_s"] = spec.test_timeout_s
    if spec.markers:
        meta["markers"] = dict(spec.markers)
    if spec.allowed_packages:
        meta["allowed_packages"] = spec.allowed_packages
    if spec.line_limit != 200:
        meta["line_limit"] = spec.line_limit
    if spec.hidden_test_hints:
        meta["hidden_test_hints"] = dict(spec.hidden_test_hints)
    if any(spec.wrong_solutions.values()):
        meta["wrong_solutions"] = {k: v for k, v in spec.wrong_solutions.items() if v}
    if spec.hints:
        meta["hints"] = spec.hints
    if spec.output_file:
        meta["output_file"] = spec.output_file

    class _Dumper(yaml.SafeDumper):
        pass

    def _str(dumper, value):  # multi-line text as a readable | block
        style = "|" if "\n" in value else None
        return dumper.represent_scalar("tag:yaml.org,2002:str", value, style=style)

    _Dumper.add_representer(str, _str)
    return yaml.dump(meta, Dumper=_Dumper, sort_keys=False, allow_unicode=True)


def to_folder_files(spec: TaskSpec) -> dict[str, str]:
    """The task as {relative path: text}, the inverse of parse_task()."""
    out = {"task.yaml": task_yaml(spec)}
    if spec.requirements:
        out["requirements.txt"] = "\n".join(spec.requirements) + "\n"
    for f in spec.files:
        out[f"{_ROLE_DIRS[f.role]}/{f.path}"] = f.content
    for case in spec.stdout_cases:
        folder = f"{'tests' if case.visible else 'hidden_tests'}/{case.name}"
        out[f"{folder}/stdin.txt"] = case.stdin
        out[f"{folder}/expected_stdout.txt"] = case.expected_stdout
        for fl in case.files:
            out[f"{folder}/files/{fl['name']}"] = fl["content"]
    return out


def to_zip(spec: TaskSpec) -> bytes:
    """A zip with one top-level folder named after the task id (what load_task_zip reads)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, content in sorted(to_folder_files(spec).items()):
            z.writestr(f"{spec.id}/{rel}", content)
    return buf.getvalue()


if __name__ == "__main__":
    # python -m backend.task_format path/to/<task-id> [more folders or zips...]
    import sys

    status = 0
    for target in sys.argv[1:]:
        try:
            if os.path.isdir(target):
                spec = load_task_dir(target)
            else:
                with open(target, "rb") as f:
                    spec = load_task_zip(f.read(), default_id=os.path.splitext(os.path.basename(target))[0])
        except TaskFormatError as e:
            status = 1
            print(f"{target}: {len(e.problems)} problem(s)")
            for p in e.problems:
                print(f"  - {p}")
            continue
        tests = {r: len(spec.files_with_role(r)) for r in ("test", "hidden_test")}
        print(f"{target}: OK -- {spec.title!r}, {spec.language}, grading {spec.grading}, editable "
              f"{', '.join(spec.editable)}, {tests['test']} visible / {tests['hidden_test']} hidden test file(s)"
              if spec.grading == "tests" else
              f"{target}: OK -- {spec.title!r}, {spec.language}, grading stdout, {len(spec.stdout_cases)} tests")
    sys.exit(status)
