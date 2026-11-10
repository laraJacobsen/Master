#!/usr/bin/env python3
"""End-to-end load test: one simulated lecture against the real backend and the
real local Judge0, with the LLM Label call stubbed, real, or off.

Each run starts its own backend (uvicorn on port 8200, LOADTEST_TIMING=1) on a
fresh SQLite file inside the run's results folder, so the dev database is never
opened and the backend's in-memory label caches start cold. Then:

  - every simulated student joins, polls /api/lecture/status every 2 s and
    heartbeats every 10 s for the whole run (as student/App.tsx does), and
    submits per its plan (see workload.py);
  - one simulated lecturer fires the dashboard's six polls every 3 s without
    waiting for the previous ones (setInterval, as lecturer/App.tsx does),
    through a 6-connection pool like a browser's per-host limit;
  - the machine is sampled once a second (sysmon.py).

Measured: submit->verdict latency per submission (POST /api/submit is
synchronous), with the server's per-stage split from LOADTEST_TIMING;
verdict->visible on the dashboard per submission; and per batch, when
/api/lecturer/clusters first reflects every student's latest submission with
every wrong-answer group of 2+ students labelled.

Scenarios: single, calibrate, steady, burst, resubmit, legacy (see workload.py).

Run: python3 loadtest/run.py --scenario single --provisional "heavy apps open"
"""

import argparse
import asyncio
import csv
import json
import os
import platform
import random
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(REPO))

import sysmon  # noqa: E402
import workload  # noqa: E402
from backend import hints  # noqa: E402  (fallback label text, to tell it from a model's)

BACKEND_PORT = 8200
STUB_PORT = 8299
BASE = f"http://127.0.0.1:{BACKEND_PORT}"
JUDGE0 = os.environ.get("JUDGE0_BASE_URL", "http://localhost:2358")
JUDGE0_CONTAINER = "judge0-v1131_workers_1"

STATUS_POLL_S = 2  # POLL_MS in student/App.tsx
HEARTBEAT_S = 10  # HEARTBEAT_MS in student/App.tsx
LECTURER_POLL_S = 3  # POLL_MS in lecturer/App.tsx
LECTURER_MAX_CONNECTIONS = 6  # a browser's HTTP/1.1 per-host limit
APP_DEFAULT_MAX_CONCURRENT_SUBMITS = 16  # backend/main.py

# Pass/fail targets (raw numbers are always reported too).
TARGETS = {
    "steady_p95_submit_s": 5.0,
    "burst_p95_submit_s": 10.0,
    "dp_ready_after_time_up_s": 30.0,
    "max_error_timeout_rate": 0.02,
}
# Stop a run early when errors/timeouts dominate.
STOP_RULE = {"min_completed": 10, "max_error_timeout_share": 0.20}
# How long the lecturer keeps polling for discussion points after the last verdict.
DP_WAIT_CAP_S = 90.0

STUB_MARKER = "[stub]"


# --------------------------------------------------------------------------- helpers


def pct(values, p):
    """Percentile with linear interpolation between closest ranks (numpy's default)."""
    v = sorted(values)
    if not v:
        return None
    k = (len(v) - 1) * p / 100
    lo, hi = int(k), min(int(k) + 1, len(v) - 1)
    return v[lo] + (v[hi] - v[lo]) * (k - lo)


def stats(values):
    v = [x for x in values if x is not None]
    if not v:
        return {"n": 0, "p50": None, "p95": None, "p99": None, "max": None}
    return {"n": len(v), "p50": pct(v, 50), "p95": pct(v, 95), "p99": pct(v, 99), "max": max(v)}


def fmt(x, nd=2):
    return "–" if x is None else f"{x:.{nd}f}"


def sh(cmd, timeout=15):
    try:
        return subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=timeout).stdout.strip()
    except subprocess.SubprocessError:
        return ""


# --------------------------------------------------------------------------- run state


class Run:
    def __init__(self, args, plans, question, calibration):
        self.args = args
        self.plans = plans
        self.question = question
        self.calibration = calibration
        self.t0 = time.perf_counter()
        self.task_t0 = None  # perf_counter when the question started
        self.requests = []
        self.submissions = []
        self.cluster_snaps = []
        self.first_seen = {}  # submission id -> rel time first seen in /api/lecturer/submissions
        self.abort = asyncio.Event()
        self.abort_reason = None
        self.students_finished = 0  # students whose plan has run out
        self.skipped_after_time_up = 0
        self.students_done = asyncio.Event()
        self.bg_stop = asyncio.Event()  # student polls/heartbeats
        self.lecturer_stop = asyncio.Event()
        self.qid = None

    def rel(self, t):
        return round(t - self.t0, 4)

    async def call(self, client, actor, endpoint, method, path, **kw):
        t_start = time.perf_counter()
        outcome, status, data, err = "ok", None, None, ""
        try:
            r = await client.request(method, f"{BASE}{path}", **kw)
            status = r.status_code
            if r.is_success:
                data = r.json()
            else:
                outcome, err = "http_error", r.text[:200]
        except httpx.TimeoutException as e:
            outcome, err = "timeout", type(e).__name__
        except httpx.HTTPError as e:
            outcome, err = "transport_error", f"{type(e).__name__}: {e}"[:200]
        t_end = time.perf_counter()
        self.requests.append(
            {
                "actor": actor,
                "endpoint": endpoint,
                "t_start": self.rel(t_start),
                "t_end": self.rel(t_end),
                "latency_s": round(t_end - t_start, 4),
                "status": status,
                "outcome": outcome,
                "error": err,
            }
        )
        return data, t_start, t_end, outcome

    def check_stop_rule(self):
        done = [s for s in self.submissions]
        if len(done) < STOP_RULE["min_completed"] or self.abort.is_set():
            return
        bad = sum(1 for s in done if s["outcome"] != "ok")
        if bad / len(done) > STOP_RULE["max_error_timeout_share"]:
            self.abort_reason = (
                f"stopped: {bad}/{len(done)} submits failed or timed out "
                f"(> {STOP_RULE['max_error_timeout_share']:.0%})"
            )
            self.abort.set()


async def every(interval, fn, stop: asyncio.Event, phase=0.0, overlap=True):
    """Call fn() every `interval` s until stop. overlap=True fires on schedule
    whether or not the previous call returned (a browser's setInterval)."""
    pending = set()
    try:
        await asyncio.wait_for(stop.wait(), timeout=phase)
        return
    except asyncio.TimeoutError:
        pass
    while not stop.is_set():
        if overlap:
            t = asyncio.create_task(fn())
            pending.add(t)
            t.add_done_callback(pending.discard)
        else:
            await fn()
        try:
            await asyncio.wait_for(stop.wait(), timeout=interval)
        except asyncio.TimeoutError:
            pass
    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


async def sleep_until(t_abs, abort: asyncio.Event):
    """Sleep until perf_counter() >= t_abs; returns False if aborted first."""
    delay = t_abs - time.perf_counter()
    if delay <= 0:
        return not abort.is_set()
    try:
        await asyncio.wait_for(abort.wait(), timeout=delay)
        return False
    except asyncio.TimeoutError:
        return True


# --------------------------------------------------------------------------- actors


async def student(run: Run, client, plan: workload.StudentPlan, rng: random.Random):
    edited = {"v": True}

    async def poll_status():
        await run.call(client, plan.name, "status", "GET", "/api/lecture/status")

    async def heartbeat():
        await run.call(
            client, plan.name, "activity", "POST", "/api/lecture/activity",
            json={"student_name": plan.name, "question_id": run.qid, "edited": edited["v"]},
        )

    overlap = run.args.scenario != "legacy"  # load_test.py's threads waited for each poll
    bg = [
        asyncio.create_task(every(STATUS_POLL_S, poll_status, run.bg_stop, rng.uniform(0, STATUS_POLL_S), overlap)),
        asyncio.create_task(every(HEARTBEAT_S, heartbeat, run.bg_stop, rng.uniform(0, HEARTBEAT_S), overlap)),
    ]

    solved = False
    for i, step in enumerate(plan.steps):
        if step.only_if_failed and solved:
            break
        time_up = run.task_t0 + run.question["duration_seconds"]
        if step.at is not None:
            at = run.task_t0 + step.at
        else:
            at = time.perf_counter() + step.think_s
            # A resubmit can't happen after time-up: the student page switches to
            # the waiting screen. (The time-up auto-submit is a planned first step.)
            if at > time_up:
                run.skipped_after_time_up += 1
                break
        if not await sleep_until(at, run.abort):
            break
        data, t_s, t_e, outcome = await run.call(
            client, plan.name, "submit", "POST", "/api/submit",
            json={"student_name": plan.name, "question_id": run.qid, "source_code": workload.code_for(step.entry_id)},
        )
        edited["v"] = False
        expected = workload.expected_for(step.entry_id, run.calibration)
        timing = (data or {}).get("_timing") or {}
        verdict = (data or {}).get("verdict")
        tests_passed = (data or {}).get("tests_passed")
        verdict_ok = None
        if expected and outcome == "ok":
            verdict_ok = verdict == expected["verdict"] and (
                expected.get("tests_passed") is None or tests_passed == expected["tests_passed"]
            )
        run.submissions.append(
            {
                "student": plan.name,
                "step": i + 1,
                "attempt_number": (data or {}).get("attempt_number"),
                "entry_id": step.entry_id,
                "category": step.category,
                "submission_id": (data or {}).get("submission_id"),
                "t_submit": run.rel(t_s),
                "t_verdict": run.rel(t_e),
                "t_submit_vs_time_up": round(t_s - time_up, 3),
                "latency_s": round(t_e - t_s, 4),
                "outcome": outcome,
                "verdict": verdict,
                "tests_passed": tests_passed,
                "expected_verdict": (expected or {}).get("verdict"),
                "expected_tests_passed": (expected or {}).get("tests_passed"),
                "verdict_ok": verdict_ok,
                "slot_wait_s": timing.get("slot_wait_s"),
                "prep_s": timing.get("prep_s"),
                "judge0_calls_s": ";".join(f"{x:.4f}" for x in timing.get("judge0_calls_s", [])),
                "judge0_total_s": timing.get("judge0_total_s"),
                "classify_s": timing.get("classify_s"),
                "db_write_s": timing.get("db_write_s"),
                "server_total_s": timing.get("server_total_s"),
                "client_minus_server_s": (
                    round((t_e - t_s) - timing["server_total_s"], 4) if "server_total_s" in timing else None
                ),
            }
        )
        solved = verdict == "correct"
        run.check_stop_rule()
    run.students_finished += 1
    await run.students_done.wait()
    await asyncio.gather(*bg)


def _fallback_wa(count):
    try:
        return hints.discussion_point_for_cluster("wrong_answer", None, count)
    except Exception:
        return None


async def lecturer(run: Run, client):
    qid = run.qid

    async def p_submissions():
        data, _, t_e, outcome = await run.call(
            client, "lecturer", "lecturer:submissions", "GET", "/api/lecturer/submissions", params={"question_id": qid}
        )
        if outcome == "ok":
            for row in data:
                run.first_seen.setdefault(row["id"], run.rel(t_e))

    async def p_clusters():
        data, t_s, t_e, outcome = await run.call(
            client, "lecturer", "lecturer:clusters", "GET", "/api/lecturer/clusters", params={"question_id": qid}
        )
        if outcome != "ok":
            return
        covered, wa_need, wa_missing, llm, fallback = set(), 0, 0, 0, 0
        for c in data:
            covered.update(c.get("submission_ids") or [])
            if c["exec_verdict"] == "wrong_answer" and (c["count"] >= 2 or c.get("raised")):
                wa_need += 1
                dp = c.get("discussion_point")
                if not dp:
                    wa_missing += 1
                elif dp.startswith(STUB_MARKER) or (run.args.llm == "real" and dp != _fallback_wa(c["count"])):
                    llm += 1
                else:
                    fallback += 1
        run.cluster_snaps.append(
            {
                "t_start": run.rel(t_s),
                "t_end": run.rel(t_e),
                "latency_s": round(t_e - t_s, 4),
                "n_clusters": len(data),
                "covered_ids": covered,
                "wa_groups_needing_label": wa_need,
                "wa_labels_missing": wa_missing,
                "wa_labels_llm": llm,
                "wa_labels_fallback": fallback,
            }
        )

    def simple(endpoint, path):
        async def f():
            await run.call(client, "lecturer", endpoint, "GET", path)
        return f

    polls = [p_submissions, p_clusters]
    if run.args.scenario == "legacy":  # load_test.py's lecturer: four endpoints, one after another
        polls += [
            simple("lecturer:progress", f"/api/lecturer/questions/{qid}/progress"),
            simple("lecturer:activity", f"/api/lecturer/questions/{qid}/activity"),
        ]

        async def sequential():
            for p in polls:
                await p()

        await every(LECTURER_POLL_S, sequential, run.lecturer_stop, 0, overlap=False)
        return
    polls += [
        simple("lecturer:progress", f"/api/lecturer/questions/{qid}/progress"),
        simple("lecturer:question", f"/api/lecturer/questions/{qid}"),
        simple("lecturer:activity", f"/api/lecturer/questions/{qid}/activity"),
        simple("lecturer:active_lecture", "/api/lecturer/lectures/active"),
    ]
    await asyncio.gather(*(every(LECTURER_POLL_S, p, run.lecturer_stop, 0, overlap=True) for p in polls))


def latest_ids(submissions):
    latest = {}
    for s in submissions:
        if s["outcome"] == "ok" and s["submission_id"] is not None:
            if s["student"] not in latest or s["submission_id"] > latest[s["student"]]:
                latest[s["student"]] = s["submission_id"]
    return set(latest.values())


def dp_ready_snapshot(snaps, ids):
    for snap in sorted(snaps, key=lambda s: s["t_end"]):
        if ids <= snap["covered_ids"] and snap["wa_labels_missing"] == 0:
            return snap
    return None


# --------------------------------------------------------------------------- setup


def start_stub(run_dir, latency):
    log = open(run_dir / "llm_stub.log", "w")
    proc = subprocess.Popen(
        [sys.executable, str(HERE / "llm_stub.py"), "--port", str(STUB_PORT), "--latency", str(latency)],
        stdout=log, stderr=subprocess.STDOUT,
    )
    for _ in range(50):
        try:
            httpx.get(f"http://127.0.0.1:{STUB_PORT}/stats", timeout=1)
            return proc
        except httpx.HTTPError:
            time.sleep(0.1)
    proc.terminate()
    sys.exit("LLM stub didn't start.")


def read_idun_key():
    path = REPO / ".idun.env"
    for line in path.read_text().splitlines():
        if line.startswith("IDUN_API_KEY="):
            return line.split("=", 1)[1].strip().strip('"')
    sys.exit("No IDUN_API_KEY in .idun.env")


def start_backend(run_dir, args):
    env = dict(os.environ, PROTOTYPE_DB_PATH=str(run_dir / "backend.db"), LOADTEST_TIMING="1", LLM_PROVIDER="idun")
    if args.llm == "stub":
        env.update(IDUN_BASE_URL=f"http://127.0.0.1:{STUB_PORT}/v1", IDUN_API_KEY="loadtest-stub")
    elif args.llm == "real":
        env["IDUN_API_KEY"] = read_idun_key()
    else:  # off: no key -> backend skips the call and uses the fallback text
        env["IDUN_API_KEY"] = ""
    if args.max_concurrent_submits is not None:
        env["MAX_CONCURRENT_SUBMITS"] = str(args.max_concurrent_submits)
    else:
        env.pop("MAX_CONCURRENT_SUBMITS", None)
    log = open(run_dir / "backend.log", "w")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.main:app", "--port", str(BACKEND_PORT), "--log-level", "warning"],
        cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT,
    )
    for _ in range(120):
        try:
            httpx.get(f"{BASE}/api/questions", timeout=1)
            return proc
        except httpx.HTTPError:
            if proc.poll() is not None:
                sys.exit(f"Backend exited; see {run_dir / 'backend.log'}")
            time.sleep(0.5)
    proc.terminate()
    sys.exit("Backend didn't come up.")


def setup_lecture(client: httpx.Client, args, question_def, duration):
    def api(method, path, **kw):
        r = client.request(method, f"{BASE}{path}", timeout=120, **kw)
        r.raise_for_status()
        return r.json()

    if api("GET", "/api/lecturer/lectures/active")["lecture"]:
        api("POST", "/api/lecturer/lecture/finish", json={})
    lecture = api("POST", "/api/lecturer/lectures", json={"label": f"LOADTEST {args.scenario} n={args.students}"})
    lecture = api("POST", f"/api/lecturer/lectures/{lecture['id']}/open_lobby")
    q = api(
        "POST", "/api/lecturer/questions",
        json={**question_def, "expected_students": args.students, "duration_seconds": duration},
    )
    if not api("POST", f"/api/lecturer/questions/{q['id']}/validate")["validated"]:
        sys.exit("Question failed validation against Judge0.")
    return lecture, q["id"], api


# --------------------------------------------------------------------------- conditions


def judge0_conditions():
    try:
        config = httpx.get(f"{JUDGE0}/config_info", timeout=5).json()
        about = httpx.get(f"{JUDGE0}/about", timeout=5).json()
    except httpx.HTTPError as e:
        sys.exit(f"Judge0 isn't reachable at {JUDGE0} ({e}).")
    procs = sh(f"docker exec {JUDGE0_CONTAINER} sh -c 'ps aux | grep -c \"[r]esque-2.0.0\"'")
    count_env = sh(f"docker exec {JUDGE0_CONTAINER} sh -c 'grep -o \"COUNT=.*\" /api/environment | head -1'")
    keys = ["cpu_time_limit", "max_cpu_time_limit", "cpu_extra_time", "wall_time_limit", "max_wall_time_limit",
            "memory_limit", "max_memory_limit", "stack_limit", "max_queue_size", "max_processes_and_or_threads",
            "enable_network", "number_of_runs"]
    return {
        "version": about.get("version"),
        "worker_processes": int(procs) if procs.isdigit() else None,
        "COUNT": count_env.split("=", 1)[1].strip('"') if "=" in count_env else None,
        "config": {k: config.get(k) for k in keys},
    }


def docker_mem():
    out = sh("docker stats --no-stream --format '{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}'", timeout=20)
    return [line.split("\t") for line in out.splitlines() if "judge0" in line]


def machine_conditions():
    lscpu = sh("lscpu")
    get = lambda key: next((l.split(":", 1)[1].strip() for l in lscpu.splitlines() if l.startswith(key)), None)  # noqa: E731
    sockets = int(get("Socket(s)") or 1)
    cores = int(get("Core(s) per socket") or 0) * sockets
    return {
        "cpu_model": get("Model name"),
        "physical_cores": cores,
        "logical_cpus": os.cpu_count(),
        "kernel": platform.release(),
        "python": platform.python_version(),
        "httpx": httpx.__version__,
        **{f"pre_run_{k}": v for k, v in sysmon.machine_snapshot().items()},
    }


def git_info():
    sha = sh(f"git -C {REPO} rev-parse --short HEAD")
    dirty = bool(sh(f"git -C {REPO} status --porcelain -- backend"))
    return {"commit": sha, "backend_dirty": dirty}


# --------------------------------------------------------------------------- analysis


def analyse(run: Run, stub_calls, backend_log: str):
    subs = run.submissions
    ok = [s for s in subs if s["outcome"] == "ok"]
    n_err = sum(1 for s in subs if s["outcome"] in ("http_error", "transport_error"))
    n_timeout = sum(1 for s in subs if s["outcome"] == "timeout")
    mismatches = [s for s in ok if s["verdict_ok"] is False]
    unchecked = sum(1 for s in ok if s["verdict_ok"] is None)
    for s in subs:
        seen = run.first_seen.get(s["submission_id"])
        s["visible_after_verdict_s"] = round(seen - s["t_verdict"], 4) if seen is not None else None

    stage = lambda key: stats([s[key] for s in ok])  # noqa: E731
    judge0_calls = [float(x) for s in ok for x in s["judge0_calls_s"].split(";") if x]
    out = {
        "submits": len(subs),
        "students": len({s["student"] for s in subs}),
        "errors": n_err,
        "timeouts": n_timeout,
        "error_timeout_rate": (n_err + n_timeout) / len(subs) if subs else None,
        "verdict_mismatches": len(mismatches),
        "verdict_unchecked": unchecked,
        "resubmits_skipped_after_time_up": run.skipped_after_time_up,
        "latency": stage("latency_s"),
        "stages": {
            k: stage(k)
            for k in ["slot_wait_s", "prep_s", "judge0_total_s", "classify_s", "db_write_s", "server_total_s",
                      "client_minus_server_s"]
        },
        "judge0_call": stats(judge0_calls),
        "visible_after_verdict": stats([s["visible_after_verdict_s"] for s in ok]),
        "by_category": {
            cat: stats([s["latency_s"] for s in ok if s["category"] == cat])
            for cat in sorted({s["category"] for s in ok})
        },
    }

    # Per-batch: dashboard reflects every student's latest submission, labels in place.
    ids = latest_ids(subs)
    t_last_verdict = max((s["t_verdict"] for s in ok), default=None)
    time_up = run.rel(run.task_t0 + run.question["duration_seconds"])
    snap = dp_ready_snapshot(run.cluster_snaps, ids) if ids else None
    final = max(run.cluster_snaps, key=lambda s: s["t_end"]) if run.cluster_snaps else None
    out["batch"] = {
        "students_with_verdict": len(ids),
        "t_last_verdict": t_last_verdict,
        "t_time_up": time_up,
        "ready": snap is not None,
        "t_ready": snap["t_end"] if snap else None,
        "ready_after_last_verdict_s": round(snap["t_end"] - t_last_verdict, 3) if snap else None,
        "ready_after_time_up_s": round(snap["t_end"] - time_up, 3) if snap else None,
        "wa_groups_needing_label": final["wa_groups_needing_label"] if final else 0,
        "wa_labels_llm_final": final["wa_labels_llm"] if final else 0,
        "wa_labels_fallback_final": final["wa_labels_fallback"] if final else 0,
    }

    # Overlapping dashboard polls: /clusters calls still in flight when the next one fired.
    cl = sorted((r for r in run.requests if r["endpoint"] == "lecturer:clusters"), key=lambda r: r["t_start"])
    events = sorted([(r["t_start"], 1) for r in cl] + [(r["t_end"], -1) for r in cl])
    cur = peak = 0
    for _, d in events:
        cur += d
        peak = max(peak, cur)
    overlapped = sum(1 for i, r in enumerate(cl) if any(p["t_end"] > r["t_start"] for p in cl[:i]))
    out["clusters_endpoint"] = {
        **stats([r["latency_s"] for r in cl]),
        "polls": len(cl),
        "started_while_previous_in_flight": overlapped,
        "max_in_flight": peak,
    }

    # LLM calls: backend log has one line per sub-cluster label (incl. its retry).
    llm_lines = re.findall(r"wrong_answer sub-cluster LLM call \((\w+)\): (\d+) snippets, ([\d.]+)s, used_model=(\w+)",
                           backend_log)
    out["llm"] = {
        "label_calls_logged": len(llm_lines),
        "label_call_latency": stats([float(x[2]) for x in llm_lines]),
        "label_calls_used_model": sum(1 for x in llm_lines if x[3] == "True"),
    }
    if stub_calls is not None:
        by_sha = {}
        for c in stub_calls:
            by_sha.setdefault(c["prompt_sha"], []).append(c)
        concurrent_dupes = sequential_repeats = 0
        for calls in by_sha.values():
            calls.sort(key=lambda c: c["t_start"])
            for i, c in enumerate(calls[1:], 1):
                if any(p["t_end"] > c["t_start"] for p in calls[:i]):
                    concurrent_dupes += 1
                else:
                    sequential_repeats += 1
        out["llm"].update(
            {
                "stub_http_calls": len(stub_calls),
                "distinct_prompts": len(by_sha),
                "identical_prompt_while_in_flight": concurrent_dupes,
                "identical_prompt_after_done": sequential_repeats,
                "max_concurrent_stub_calls": max((c["in_flight_at_start"] for c in stub_calls), default=0),
            }
        )
    out["mismatch_examples"] = [
        {k: s[k] for k in ("student", "entry_id", "verdict", "tests_passed", "expected_verdict", "expected_tests_passed")}
        for s in mismatches[:10]
    ]
    return out


def pass_fail(scenario, res):
    checks = []
    lat = res["latency"]["p95"]
    if scenario in ("steady", "resubmit"):
        checks.append(("p95 submit→verdict ≤ 5 s", lat is not None and lat <= TARGETS["steady_p95_submit_s"], lat))
    if scenario in ("burst", "legacy"):
        checks.append(("p95 submit→verdict ≤ 10 s", lat is not None and lat <= TARGETS["burst_p95_submit_s"], lat))
    if scenario in ("burst", "steady", "resubmit"):
        dp = res["batch"]["ready_after_time_up_s"]
        checks.append(("discussion points ready ≤ 30 s after time-up",
                       dp is not None and dp <= TARGETS["dp_ready_after_time_up_s"], dp))
    rate = res["error_timeout_rate"]
    checks.append(("error/timeout rate < 2%", rate is not None and rate < TARGETS["max_error_timeout_rate"], rate))
    if res["verdict_unchecked"] and res["verdict_unchecked"] == res["submits"] - res["errors"] - res["timeouts"]:
        checks.append(("no verdict mismatches", None, "unchecked (no calibration)"))
    else:
        checks.append(("no verdict mismatches", res["verdict_mismatches"] == 0,
                       f"{res['verdict_mismatches']} ({res['verdict_unchecked']} unchecked)"))
    return checks


def write_summary(run_dir, cond, res, checks):
    L = []
    rep = cond["reportable"]
    n = cond["scenario"]["students"]
    L.append(f"# Load test: {cond['scenario']['name']}, {n} student{'s' if n != 1 else ''}\n")
    if not rep["reportable"]:
        L.append(f"> **NOT FOR REPORTING** — {'; '.join(rep['reasons'])}\n")
    if cond.get("aborted"):
        L.append(f"> **Run stopped early** — {cond['aborted']}\n")
    j = cond["judge0"]
    L.append(
        f"Judge0 {j['version']}: COUNT={j['COUNT']} ({j['worker_processes']} worker processes), "
        f"MAX_CONCURRENT_SUBMITS={cond['backend']['MAX_CONCURRENT_SUBMITS']}"
        + (" — higher than the worker count, so submits queue inside Judge0"
           if (j["worker_processes"] or 0) < cond["backend"]["MAX_CONCURRENT_SUBMITS"] else "")
        + f". Question limits: CPU {cond['question']['cpu_time_limit_s']} s, memory "
        f"{cond['question']['memory_limit_kb']} kB, {cond['question']['test_cases']} tests/submission. "
        f"LLM: {cond['llm']['mode']}"
        + (f" ({cond['llm']['stub_latency_s']} s fixed)" if cond["llm"]["mode"] == "stub" else "")
        + f". Machine: {cond['machine']['cpu_model']}, {cond['machine']['physical_cores']} cores / "
        f"{cond['machine']['logical_cpus']} threads, {cond['machine']['pre_run_mem_total_mb']} MB RAM "
        f"({cond['machine']['pre_run_mem_available_mb']} MB available, "
        f"{cond['machine']['pre_run_swap_used_mb']} MB swap used at start).\n"
    )
    L.append("## Submit → verdict (s)\n")
    L.append("| n | p50 | p95 | p99 | max | errors | timeouts | verdict mismatches |")
    L.append("|---|---|---|---|---|---|---|---|")
    lat = res["latency"]
    L.append(f"| {lat['n']} | {fmt(lat['p50'])} | {fmt(lat['p95'])} | {fmt(lat['p99'])} | {fmt(lat['max'])} | "
             f"{res['errors']} | {res['timeouts']} | {res['verdict_mismatches']} |")
    L.append("\n## Server-side stages (s, LOADTEST_TIMING)\n")
    L.append("| stage | p50 | p95 | max |")
    L.append("|---|---|---|---|")
    for k, v in res["stages"].items():
        L.append(f"| {k} | {fmt(v['p50'], 4)} | {fmt(v['p95'], 4)} | {fmt(v['max'], 4)} |")
    jc = res["judge0_call"]
    L.append(f"| one Judge0 call (n={jc['n']}) | {fmt(jc['p50'], 4)} | {fmt(jc['p95'], 4)} | {fmt(jc['max'], 4)} |")
    L.append("\n## Lecturer side\n")
    v = res["visible_after_verdict"]
    L.append(f"- Verdict → visible in submissions list: p50 {fmt(v['p50'])} s, p95 {fmt(v['p95'])} s, "
             f"max {fmt(v['max'])} s (3 s poll interval)")
    b = res["batch"]
    has_deadline = cond["scenario"]["name"] in ("steady", "burst", "resubmit")
    L.append(f"- Dashboard reflects the batch with labels: "
             + (f"{fmt(b['ready_after_last_verdict_s'])} s after the last verdict"
                + (f", {fmt(b['ready_after_time_up_s'])} s after time-up" if has_deadline else "")
                if b["ready"] else "**not within the wait cap**"))
    L.append(f"- Wrong-answer groups needing a label at the end: {b['wa_groups_needing_label']} "
             f"(model: {b['wa_labels_llm_final']}, fallback: {b['wa_labels_fallback_final']})")
    c = res["clusters_endpoint"]
    L.append(f"- /api/lecturer/clusters: {c['polls']} polls, p50 {fmt(c['p50'])} s, p95 {fmt(c['p95'])} s, "
             f"max {fmt(c['max'])} s; {c['started_while_previous_in_flight']} started while an earlier one was "
             f"still in flight (max {c['max_in_flight']} at once)")
    llm = res["llm"]
    L.append(f"- Label calls (backend log): {llm['label_calls_logged']}, used model {llm['label_calls_used_model']}")
    if "stub_http_calls" in llm:
        L.append(f"- LLM HTTP calls: {llm['stub_http_calls']} for {llm['distinct_prompts']} distinct prompts; "
                 f"identical prompt re-sent while one was in flight: {llm['identical_prompt_while_in_flight']}, "
                 f"after one had finished: {llm['identical_prompt_after_done']}")
    m = cond["machine_eval"]
    L.append("\n## Machine\n")
    L.append(f"- Min MemAvailable {m['min_mem_available_mb']} MB, max swap-in {fmt(m['max_swap_in_kb_s'], 0)} kB/s, "
             f"max swap-out {fmt(m['max_swap_out_kb_s'], 0)} kB/s, mean CPU {m['mean_cpu_util_pct']} %, "
             f"backend RSS max {m['max_backend_rss_mb']} MB, client loop lag max {fmt(m['max_client_loop_lag_s'], 3)} s")
    L.append(f"- Machine-bound: {'**yes** — ' + '; '.join(m['machine_bound_reasons']) if m['machine_bound'] else 'no'}"
             f"; client-bound: {'**yes**' if m['client_bound'] else 'no'}")
    L.append("\n## Targets\n")
    L.append("| check | result | value |")
    L.append("|---|---|---|")
    for name, ok, val in checks:
        shown = f"{val:.1%}" if isinstance(val, float) and "rate" in name else (fmt(val) if isinstance(val, float) else val)
        L.append(f"| {name} | {'–' if ok is None else 'PASS' if ok else 'FAIL'} | {shown} |")
    (run_dir / "summary.md").write_text("\n".join(L) + "\n")


def write_csv(path, rows, fields=None):
    rows = list(rows)
    if not rows:
        path.write_text("")
        return
    fields = fields or list(rows[0].keys())
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


# --------------------------------------------------------------------------- main


async def run_load(run: Run, sample_pid):
    mon = sysmon.SysMon(run.t0, sample_pid, run.abort)
    mon_task = asyncio.create_task(mon.run())
    student_client = httpx.AsyncClient(
        timeout=httpx.Timeout(run.args.request_timeout, connect=10),
        limits=httpx.Limits(max_connections=None, max_keepalive_connections=None),
    )
    lecturer_client = httpx.AsyncClient(
        timeout=httpx.Timeout(run.args.request_timeout, connect=10),
        limits=httpx.Limits(max_connections=LECTURER_MAX_CONNECTIONS),
    )
    rng = random.Random(run.args.seed + 1)
    try:
        lect_task = asyncio.create_task(lecturer(run, lecturer_client))
        stud_tasks = [asyncio.create_task(student(run, student_client, p, rng)) for p in run.plans]

        # Every student's plan has run out (all its submits returned, or aborted).
        while run.students_finished < len(run.plans):
            await asyncio.sleep(0.2)
        # Lecturer keeps polling until the dashboard reflects the batch, or the cap.
        ids = latest_ids(run.submissions)
        deadline = time.perf_counter() + DP_WAIT_CAP_S
        while time.perf_counter() < deadline:
            if not ids or dp_ready_snapshot(run.cluster_snaps, ids):
                break
            await asyncio.sleep(0.25)
        run.lecturer_stop.set()
        run.bg_stop.set()
        run.students_done.set()
        await asyncio.gather(lect_task, *stud_tasks)
    finally:
        mon.stop()
        await mon_task
        await student_client.aclose()
        await lecturer_client.aclose()
    if mon.abort_reason:
        run.abort_reason = mon.abort_reason
    return mon.samples


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--scenario", required=True, choices=["single", "calibrate", "steady", "burst", "resubmit", "legacy"])
    ap.add_argument("--students", type=int, default=1)
    ap.add_argument("--llm", choices=["stub", "real", "off"], default=None,
                    help="default: stub (off for --scenario legacy, like load_test.py)")
    ap.add_argument("--stub-latency", type=float, default=2.0, help="seconds per stubbed LLM call")
    ap.add_argument("--window", type=float, default=120.0, help="task duration in seconds (steady/burst/resubmit)")
    ap.add_argument("--burst-share", type=float, default=0.8)
    ap.add_argument("--burst-spread", type=float, default=10.0)
    ap.add_argument("--max-concurrent-submits", type=int, default=None, help="default: the app's own (16)")
    ap.add_argument("--request-timeout", type=float, default=60.0)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--provisional", metavar="REASON", help="mark the run not-for-reporting, with this reason")
    ap.add_argument("--out", default=str(HERE / "results"))
    args = ap.parse_args()
    if args.llm is None:
        args.llm = "off" if args.scenario == "legacy" else "stub"

    rng = random.Random(args.seed)
    calibration = workload.load_calibration()
    question_def, duration = workload.PALINDROME_QUESTION, 3600
    if args.scenario == "single":
        args.students, plans = 1, workload.plans_single()
    elif args.scenario == "calibrate":
        args.students, plans = 1, workload.plans_calibrate()
    elif args.scenario == "steady":
        plans, duration = workload.plans_steady(args.students, args.window, rng), int(args.window)
    elif args.scenario == "burst":
        plans = workload.plans_burst(args.students, args.window, rng, args.burst_share, args.burst_spread)
        duration = int(args.window)
    elif args.scenario == "resubmit":
        plans, duration = workload.plans_resubmit(args.students, args.window, rng), int(args.window)
    else:
        plans, question_def = workload.plans_legacy(args.students, rng), workload.LEGACY_QUESTION
    if args.scenario == "calibrate":
        calibration = {}  # measure, don't compare
    if args.scenario not in ("calibrate", "legacy") and not calibration:
        print("note: no calibration.json yet -- verdicts won't be checked (run --scenario calibrate first)")

    judge0 = judge0_conditions()
    machine = machine_conditions()
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_dir = Path(args.out) / f"{stamp}_{args.scenario}_n{args.students}_w{judge0['COUNT']}_{args.llm}"
    run_dir.mkdir(parents=True)
    docker_before = docker_mem()

    stub = start_stub(run_dir, args.stub_latency) if args.llm == "stub" else None
    backend = start_backend(run_dir, args)
    run = None
    setup_client = httpx.Client()
    try:
        lecture, qid, api = setup_lecture(setup_client, args, question_def, duration)
        question_row = api("GET", f"/api/lecturer/questions/{qid}")
        run = Run(args, plans, {**question_def, "duration_seconds": duration}, calibration)
        run.qid = qid

        async def go():
            # Joins happen in the lobby, before the task starts.
            async with httpx.AsyncClient(timeout=60, limits=httpx.Limits(max_connections=None)) as jc:
                await asyncio.gather(*(
                    run.call(jc, p.name, "join", "POST", "/api/lecture/join",
                             json={"code": lecture["join_code"], "student_name": p.name})
                    for p in plans
                ))
                await run.call(jc, "lecturer", "start", "POST", f"/api/lecturer/questions/{qid}/start")
            run.task_t0 = time.perf_counter()
            return await run_load(run, backend.pid)

        print(f"Run {run_dir.name}: {len(plans)} students, question {qid}, duration {duration}s ...", flush=True)
        samples = asyncio.run(go())
        api("POST", "/api/lecturer/lecture/finish", json={"current_question_id": qid})
        stub_calls = httpx.get(f"http://127.0.0.1:{STUB_PORT}/stats", timeout=5).json()["calls"] if stub else None
    finally:
        setup_client.close()
        backend.terminate()
        backend.wait(timeout=15)
        if stub:
            stub.terminate()
            stub.wait(timeout=5)

    backend_log = (run_dir / "backend.log").read_text()
    res = analyse(run, stub_calls, backend_log)
    m_eval = sysmon.evaluate(samples, {"mem_available_mb": machine["pre_run_mem_available_mb"]})
    reasons = []
    if args.provisional:
        reasons.append(f"provisional: {args.provisional}")
    if m_eval["machine_bound"]:
        reasons.append("machine-bound: " + "; ".join(m_eval["machine_bound_reasons"]))
    if m_eval["client_bound"]:
        reasons.append(f"client-bound: event loop lag {m_eval['max_client_loop_lag_s']:.3f} s")
    if args.scenario == "calibrate":
        reasons.append("calibration run (verdict reference, not a load result)")

    mcs = args.max_concurrent_submits or APP_DEFAULT_MAX_CONCURRENT_SUBMITS
    cond = {
        "run": run_dir.name,
        "started": stamp,
        "scenario": {
            "name": args.scenario, "students": args.students, "window_s": duration, "seed": args.seed,
            "burst_share": args.burst_share if args.scenario == "burst" else None,
            "burst_spread_s": args.burst_spread if args.scenario == "burst" else None,
            "mix": workload.MIX if args.scenario in ("steady", "burst", "resubmit") else None,
        },
        "judge0": judge0,
        "backend": {
            "MAX_CONCURRENT_SUBMITS": mcs,
            "MAX_CONCURRENT_SUBMITS_source": "flag" if args.max_concurrent_submits else "app default",
            "uvicorn_workers": 1, "LOADTEST_TIMING": True, "db": "fresh per run (results folder)",
            **git_info(),
        },
        "question": {
            "id": qid, "title": question_def["title"],
            "cpu_time_limit_s": question_row.get("cpu_time_limit_s"),
            "memory_limit_kb": question_row.get("memory_limit_kb"),
            "test_cases": len(question_def["test_cases"]),
        },
        "llm": {
            "mode": args.llm,
            "stub_latency_s": args.stub_latency if args.llm == "stub" else None,
            "model": os.environ.get("IDUN_MODEL", "openai/gpt-oss-120b") if args.llm == "real" else None,
        },
        "client": {
            "status_poll_s": STATUS_POLL_S, "heartbeat_s": HEARTBEAT_S, "lecturer_poll_s": LECTURER_POLL_S,
            "lecturer_overlapping_polls": args.scenario != "legacy",
            "lecturer_max_connections": LECTURER_MAX_CONNECTIONS,
            "student_max_connections": "unlimited", "request_timeout_s": args.request_timeout,
            "dp_wait_cap_s": DP_WAIT_CAP_S,
        },
        "machine": machine,
        "machine_thresholds": sysmon.THRESHOLDS,
        "docker_before": docker_before,
        "docker_after": docker_mem(),
        "machine_eval": m_eval,
        "aborted": run.abort_reason,
        "targets": TARGETS,
        "stop_rule": STOP_RULE,
        "reportable": {"reportable": not reasons, "reasons": reasons},
    }
    checks = pass_fail(args.scenario, res)
    (run_dir / "conditions.json").write_text(json.dumps(cond, indent=2))
    (run_dir / "results.json").write_text(json.dumps({**res, "checks": checks}, indent=2, default=str))
    write_csv(run_dir / "submissions.csv", run.submissions)
    write_csv(run_dir / "requests.csv", run.requests)
    write_csv(run_dir / "system.csv", samples)
    write_csv(run_dir / "clusters_polls.csv",
              ({**s, "covered_ids": len(s["covered_ids"])} for s in run.cluster_snaps))
    if stub_calls is not None:
        write_csv(run_dir / "llm_calls.csv", stub_calls)
    write_summary(run_dir, cond, res, checks)

    if args.scenario == "calibrate":
        expected = {
            s["entry_id"]: {"verdict": s["verdict"], "tests_passed": s["tests_passed"], "latency_s": s["latency_s"]}
            for s in run.submissions if s["outcome"] == "ok"
        }
        workload.CALIBRATION_PATH.write_text(
            json.dumps({"from_run": run_dir.name, "question": question_def["title"], "expected": expected}, indent=2)
        )
        print(f"Wrote {workload.CALIBRATION_PATH}")
    print((run_dir / "summary.md").read_text())
    print(f"Results: {run_dir}")


if __name__ == "__main__":
    main()
