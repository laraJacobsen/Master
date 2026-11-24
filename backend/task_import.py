"""Task folder <-> question row: what an imported task becomes in the `questions` table,
and how a question (imported, or created in the setup page) is exported as a folder.

Stdout tasks map onto the columns the app always had (test_cases, starter_code,
reference_solution, output_file, hint_ladder...). Test-graded tasks keep their whole
folder in task_files, plus:
  - starter_code / reference_solution: the editable files joined into one text
    (join_files), which is what code-based features read: the starter's line-limit and
    import checks, diff-against-reference clustering, the discussion-point snippets,
    hint drafting;
  - test_cases: [] -- their tests are pytest files, not stdin/expected pairs.
"""

from __future__ import annotations

from backend.task_format import StdoutCase, TaskFile, TaskSpec

# The file a setup-page task's code lives in when it's exported.
DEFAULT_FILE_NAMES = {"python": "solution.py", "c": "main.c", "java": "Main.java", "cpp": "main.cpp"}
_COMMENT = {"python": "#", "c": "//", "java": "//", "cpp": "//"}


def file_header(path: str, language: str) -> str:
    return f"{_COMMENT.get(language, '#')} ===== {path} ====="


def join_files(files: dict[str, str], order: list[str], language: str) -> str:
    """Several editable files as one text: a single file as itself, more than one each
    under a comment header line naming it. Stored as a submission's source_code, so
    everything that reads one code string (clustering, View code, the projector)
    works unchanged for multi-file tasks."""
    paths = [p for p in order if p in files] + sorted(p for p in files if p not in order)
    if len(paths) == 1:
        return files[paths[0]]
    return "\n".join(f"{file_header(p, language)}\n{files[p].rstrip()}\n" for p in paths)


def split_files(text: str, editable: list[str], language: str) -> dict[str, str]:
    """The inverse of join_files(): one text back into {path: content}. A single
    editable file is the whole text. With several, each header line starts its file;
    text before the first header, or a text without headers, goes to the first file.
    Used when a client sends one code string for a multi-file task (the projector's
    Run on a shown attempt, one-file scripts)."""
    if len(editable) <= 1:
        return {editable[0]: text} if editable else {}
    headers = {file_header(p, language): p for p in editable}
    out: dict[str, list[str]] = {}
    current = editable[0]
    for line in text.split("\n"):
        if line.strip() in headers:
            current = headers[line.strip()]
            out.setdefault(current, [])
            continue
        out.setdefault(current, []).append(line)
    return {p: "\n".join(lines).strip("\n") + "\n" for p, lines in out.items()}


def task_files_of(spec: TaskSpec) -> list[dict]:
    return [{"path": f.path, "role": f.role, "content": f.content} for f in spec.files]


def question_fields(spec: TaskSpec) -> dict:
    """What store.create_question() needs for this task, as a draft."""
    fields = {
        "title": spec.title,
        "prompt": spec.description,
        "language": spec.language,
        "cpu_time_limit_s": spec.cpu_time_limit_s,
        "memory_limit_kb": spec.memory_limit_kb,
        "duration_seconds": spec.duration_seconds,
        "line_limit": spec.line_limit,
        "extra_packages": spec.extra_packages,
        "hint_ladder": spec.hints or None,
        "grading_mode": spec.grading,
        "task_meta": {
            "id": spec.id,
            "editable": spec.editable,
            "markers": spec.markers,
            "test_timeout_s": spec.test_timeout_s,
            "requirements": spec.requirements,
            "allowed_packages": spec.allowed_packages,
        },
    }
    starter = {f.path: f.content for f in spec.files_with_role("starter")}
    reference = {f.path: f.content for f in spec.files_with_role("reference")}
    if spec.grading == "stdout":
        name = spec.editable[0]
        fields.update(
            test_cases=[{"stdin": c.stdin, "expected_stdout": c.expected_stdout, "files": c.files}
                        for c in spec.stdout_cases],
            starter_code=starter.get(name),
            reference_solution=reference[name],
            output_file=spec.output_file,
            task_files=None,
        )
        fields["task_meta"]["case_names"] = [c.name for c in spec.stdout_cases]
    else:
        fields.update(
            test_cases=[],
            starter_code=join_files({p: starter[p] for p in spec.editable if p in starter}, spec.editable, spec.language),
            reference_solution=join_files(reference, spec.editable, spec.language),
            output_file=None,
            task_files=task_files_of(spec),
        )
    return fields


def spec_of_question(q: dict) -> TaskSpec:
    """A question row as a TaskSpec, for export -- the inverse of question_fields()."""
    meta = q.get("task_meta") or {}
    language = q["language"]
    spec = TaskSpec(
        id=meta.get("id") or q["id"],
        title=q["title"],
        description=q["prompt"],
        language=language,
        grading=q.get("grading_mode") or "stdout",
        editable=list(meta.get("editable") or [DEFAULT_FILE_NAMES.get(language, "solution.py")]),
        # task.yaml's ranges, so whatever the setup page allowed still loads back.
        cpu_time_limit_s=min(max(q["cpu_time_limit_s"], 0.5), 15),
        memory_limit_kb=min(max(q["memory_limit_kb"], 16 * 1024), 250 * 1024),
        test_timeout_s=meta.get("test_timeout_s", 2),
        duration_seconds=min(max(q.get("duration_seconds") or 600, 60), 180 * 60),
        markers=meta.get("markers"),
        line_limit=q.get("line_limit") or 200,
        hints=list(q.get("hint_ladder") or []),
        output_file=q.get("output_file"),
        requirements=list(meta.get("requirements") or []),
        allowed_packages=list(meta.get("allowed_packages") or []),
    )
    if spec.grading == "tests":
        spec.files = [TaskFile(f["path"], f["role"], f["content"]) for f in q.get("task_files") or []]
        return spec

    # A setup-page task: its packages allow-list has no requirements.txt to come from.
    if not spec.allowed_packages and q.get("extra_packages"):
        spec.allowed_packages = list(q["extra_packages"])
    name = spec.editable[0]
    if q.get("starter_code") is not None:
        spec.files.append(TaskFile(name, "starter", q["starter_code"]))
    if q.get("reference_solution"):
        spec.files.append(TaskFile(name, "reference", q["reference_solution"]))
    names = list(meta.get("case_names") or [])
    for i, case in enumerate(q["test_cases"]):
        default = "example" if i == 0 else f"test_{i:02d}"
        spec.stdout_cases.append(StdoutCase(
            name=names[i] if i < len(names) else default,
            stdin=case.get("stdin", ""),
            expected_stdout=case.get("expected_stdout", ""),
            files=[{"name": f["name"], "content": f["content"]} for f in case.get("files") or []],
            visible=i == 0,
        ))
    return spec
