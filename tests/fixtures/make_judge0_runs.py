"""Regenerates tests/fixtures/judge0_runs.json from real runs: the example pandas task with one
student solution per scenario, run through Judge0 on the judge0-pytest image. Each file
keeps what Judge0 returned (the run dict, whose stdout holds the JUnit report behind the
run's marker), so tests/test_task_runner.py checks the parser against real reports
without needing Judge0.

    python tests/fixtures/make_judge0_runs.py      # needs the local Judge0 on that image
"""

import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from backend import judge0_client, task_format, task_import, task_runner  # noqa: E402

HERE = os.path.dirname(__file__)
EXAMPLE = os.path.join(HERE, "pandas-sales-summary")

spec = task_format.load_task_dir(EXAMPLE)
fields = task_import.question_fields(spec)
reference = task_runner.reference_files(fields)["solution.py"]
starter = task_runner.starter_files(fields)["solution.py"]

SCENARIOS = {
    "all_pass": reference,
    "starter": starter,
    "syntax_error": reference.replace("return df.groupby", "return (df.groupby"),
    "import_error": reference.replace("def load_sales(", "def load_sale("),
    "missing_package": "import seaborn\n" + reference,
    "per_test_timeout": reference.replace(
        '    return df.groupby', '    import time\n    time.sleep(30)\n    return df.groupby'),
    "run_timeout": reference.replace(
        '    df = pd.read_csv(path)\n', '    df = pd.read_csv(path)\n    while True:\n        pass\n', 1),
    "memory": reference.replace(
        '    df = pd.read_csv(path)\n', '    df = pd.read_csv(path)\n    junk = bytearray(400_000_000)\n', 1),
    "exits_early": "import os\nos._exit(0)\n" + reference,
    "prints": reference.replace("    return df\n", "    print('rows:', len(df))\n    return df\n", 1),
    "prints_top_level": reference + "\nprint('loading my solution')\n",
}
# The task folder's own wrong solutions (wrong/<name>/solution.py), recorded too: the
# smoke test's fake Judge0 answers Check solution's runs of them from these.
for _name, _files in task_runner.wrong_solutions(fields).items():
    SCENARIOS[f"wrong_{_name}"] = _files["solution.py"]

# A second, tiny task whose visible and hidden test files import different functions:
# a solution missing only the hidden test's function breaks just that file's import.
TWO_FILES = task_import.question_fields(task_format.parse_task({
    "task.yaml": b"title: Two files\ndescription: d\nlanguage: python\ngrading: tests\n",
    "starter/solution.py": b"def a():\n    pass\n\n\ndef b():\n    pass\n",
    "reference/solution.py": b"def a():\n    return 1\n\n\ndef b():\n    return 2\n",
    "tests/test_a.py": b"from solution import a\n\n\ndef test_a():\n    assert a() == 1\n",
    "hidden_tests/test_b.py": b"from solution import b\n\n\ndef test_b():\n    assert b() == 2\n",
}, default_id="two-files"))
OTHER_TASKS = {"collection_error_in_one_file": (TWO_FILES, "def a():\n    return 1\n")}


def main():
    runs = {}
    real = judge0_client.run_archive
    jobs = [(name, fields, code) for name, code in SCENARIOS.items()]
    jobs += [(name, task, code) for name, (task, code) in OTHER_TASKS.items()]
    for name, task, code in jobs:
        captured = {}

        def recording(*args, **kwargs):
            captured["run"] = real(*args, **kwargs)
            return captured["run"]

        judge0_client.run_archive = recording
        try:
            results = task_runner.run_tests(task, {"solution.py": code})
        finally:
            judge0_client.run_archive = real
        run = runs[name] = captured["run"]
        summary = ", ".join(f"{r.name}={r.outcome}/{r.error_type}" for r in results)
        print(f"{name:17} {run['status_description']:24} cpu {run['time_s']}s {run['memory_kb']}KB  {summary}")

    with open(os.path.join(HERE, "judge0_runs.json"), "w") as f:
        json.dump(runs, f, indent=1, sort_keys=True)


if __name__ == "__main__":
    main()
