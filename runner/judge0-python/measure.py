"""Per-submission cost of a test-graded pandas task inside Judge0's sandbox.

Sends sequential submissions (one at a time, so nothing queues) to the local
Judge0 and reports Judge0's own CPU time, wall time and peak memory for:

  stock-py38-print   the stock Python 3.8 language (71) printing one line --
                     what a stdout-graded test run costs today, for scale
  py311-bare         Python 3.11 starting and exiting (multi-file language 89)
  py311-import       Python 3.11 importing pandas + numpy
  py311-pytest       the real thing: pytest + junit XML over a small pandas
                     solution, a CSV and 5 tests (3 visible, 2 hidden)

Rerun after changing versions.env (and build.sh + use_image.sh) to see what a
new pin costs. Needs the workers on the judge0-pytest image.

    python runner/judge0-python/measure.py [--runs 10] [--memory-kb 128000 256000]
"""

import argparse
import base64
import io
import os
import statistics
import zipfile

import requests

JUDGE0 = os.environ.get("JUDGE0_BASE_URL", "http://localhost:2358")
PY = "/usr/local/python-3.11/bin/python3.11"
FIELDS = "status,stdout,stderr,time,wall_time,memory,exit_code,message"

SOLUTION = '''import pandas as pd


def revenue_by_region(path):
    df = pd.read_csv(path)
    df["revenue"] = df["units"] * df["price"]
    return df.groupby("region")["revenue"].sum().sort_index()
'''

CSV = "region,units,price\nnorth,3,10.0\nsouth,1,5.5\nnorth,2,10.0\neast,4,2.5\n"

TESTS = '''import pandas as pd
from solution import revenue_by_region


def test_north():
    assert revenue_by_region("data/sales.csv")["north"] == 50.0


def test_regions_sorted():
    assert list(revenue_by_region("data/sales.csv").index) == ["east", "north", "south"]


def test_is_series():
    assert isinstance(revenue_by_region("data/sales.csv"), pd.Series)
'''

HIDDEN = '''from solution import revenue_by_region


def test_total():
    assert revenue_by_region("data/sales.csv").sum() == 65.5


def test_south():
    assert revenue_by_region("data/sales.csv")["south"] == 5.5
'''

ENV = "export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1\n"


def zip_b64(files: dict) -> str:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            z.writestr(name, content)
    return base64.b64encode(buf.getvalue()).decode()


def run_script(cmd: str) -> str:
    return "#!/bin/bash\n" + ENV + cmd + "\n"


SCENARIOS = {
    "stock-py38-print": {"language_id": 71, "source_code": base64.b64encode(b"print(65.5)\n").decode()},
    "py311-bare": {"language_id": 89, "additional_files": zip_b64({"run": run_script(f"{PY} -c pass")})},
    "py311-import": {"language_id": 89, "additional_files": zip_b64(
        {"run": run_script(f"{PY} -c 'import pandas, numpy'")})},
    "py311-pytest": {"language_id": 89, "additional_files": zip_b64({
        "solution.py": SOLUTION,
        "data/sales.csv": CSV,
        "tests/test_visible.py": TESTS,
        "hidden_tests/test_hidden.py": HIDDEN,
        "run": run_script(
            f"{PY} -m pytest -q -p no:cacheprovider --timeout=5 "
            "--rootdir=. --junitxml=report.xml tests hidden_tests\n"
            "status=$?\necho '@@REPORT@@'; cat report.xml\nexit $status"
        ),
    })},
}


def submit(payload: dict, memory_kb: int) -> dict:
    body = {**payload, "cpu_time_limit": 10, "wall_time_limit": 20, "memory_limit": memory_kb}
    r = requests.post(f"{JUDGE0}/submissions", params={"base64_encoded": "true", "wait": "true", "fields": FIELDS},
                      json=body, timeout=60)
    r.raise_for_status()
    return r.json()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--memory-kb", type=int, nargs="+", default=[128000, 256000])
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()

    print(f"{'scenario':18} {'mem limit':>9} {'status':22} {'CPU s med/max':>14} {'wall s med/max':>15} {'peak MB med/max':>16}")
    for mem in args.memory_kb:
        for name, payload in SCENARIOS.items():
            if args.only and name not in args.only:
                continue
            submit(payload, mem)  # warm-up, not counted
            res = [submit(payload, mem) for _ in range(args.runs)]
            statuses = {r["status"]["description"] for r in res}
            cpu = [float(r["time"] or 0) for r in res]
            wall = [float(r["wall_time"] or 0) for r in res]
            peak = [(r["memory"] or 0) / 1024 for r in res]
            print(f"{name:18} {mem // 1000:>6} MB {', '.join(sorted(statuses))[:22]:22} "
                  f"{statistics.median(cpu):6.2f} /{max(cpu):5.2f}  {statistics.median(wall):7.2f} /{max(wall):5.2f}  "
                  f"{statistics.median(peak):7.1f} /{max(peak):6.1f}")
            if statuses != {"Accepted"}:
                bad = next(r for r in res if r["status"]["description"] != "Accepted")
                for key in ("stdout", "stderr", "message"):
                    if bad.get(key):
                        text = base64.b64decode(bad[key]).decode(errors="replace")
                        print(f"    {key}: {text[-600:]}")
            elif name == "py311-pytest":
                out = base64.b64decode(res[-1]["stdout"]).decode(errors="replace")
                print("    pytest:", out.split("@@REPORT@@")[0].strip().splitlines()[-1])


if __name__ == "__main__":
    main()
