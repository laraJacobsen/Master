# loadtest/

End-to-end load test of the lecture prototype: simulated students and a simulated lecturer
against the real backend and the real local Judge0. Tests whether a whole class's
submissions, especially the burst at time-up, stay within a lecture's time budget.

## Setup

```
pip install --user -r loadtest/requirements.txt
loadtest/judge0_workers.sh 4      # Judge0 worker count for this condition: 4, 8 or 16
```

`judge0_workers.sh` mounts a copy of `~/judge0-v1.13.1/judge0.conf` with `COUNT` set
(kept in `~/judge0-loadtest/`, outside the repo, because it holds Judge0's DB passwords) and
recreates only the workers container. `loadtest/judge0_workers.sh reset` goes back to the
original config.

## Running

```
python3 loadtest/run.py --scenario calibrate          # once: expected verdict per corpus entry
python3 loadtest/run.py --scenario single             # one student through the whole flow
python3 loadtest/run.py --scenario burst --students 50
```

| Scenario | What the class does |
|---|---|
| `single` | one student, one correct submit at t=12 s |
| `calibrate` | one student submits all 25 corpus entries in turn; writes `calibration.json` |
| `steady` | first submits uniform over the task window (`--window`, default 120 s) |
| `burst` | 80% submit within 10 s after time-up (`--burst-share`, `--burst-spread`), the rest during the window |
| `resubmit` | first submits over the first half of the window; failures resubmit 1–2 times after 15–45 s, never after time-up |
| `legacy` | `load_test.py --mode burst` reproduced: its question, plans and 1 s burst, sequential polls, LLM off |

Options: `--llm stub|real|off` (default `stub`; `real` reads `IDUN_API_KEY` from `.idun.env`
and needs the NTNU network/VPN), `--stub-latency` (default 2.0 s, in line with the measured IDUN
label calls), `--max-concurrent-submits`, `--seed`, and `--provisional "reason"` to mark a run
not-for-reporting.

Each run starts its own backend on port 8200 with `LOADTEST_TIMING=1` and a fresh SQLite file
in the run's folder, so the dev database is never opened and label caches start cold.
Students poll status every 2 s and heartbeat every 10 s. The lecturer fires the dashboard's
six polls every 3 s without waiting for earlier ones (like `setInterval`), through 6
connections like a browser.

## Output (`results/<time>_<scenario>_n<N>_w<COUNT>_<llm>/`)

- `summary.md`: p50/p95/p99/max, errors, timeouts, per-stage split, lecturer-side timings,
  LLM call counts, machine state, and pass/fail against the targets.
- `conditions.json`: Judge0 COUNT and worker processes, Judge0 limits,
  MAX_CONCURRENT_SUBMITS, question limits, LLM mode, CPU/RAM, memory and swap at start,
  docker memory before and after, git commit, and whether the run is reportable and why not.
- `submissions.csv`: one row per submit, with the server's `_timing` split.
- `requests.csv`: every request.
- `system.csv`: machine samples once a second.
- `clusters_polls.csv`: one row per `/api/lecturer/clusters` poll.
- `llm_calls.csv`: stub runs only.
- `backend.log`, `backend.db`.

A run is flagged **machine-bound** (laptop, not app) when free memory or swap-in crossed the
thresholds in `sysmon.py`, and **client-bound** when the load generator's event loop fell
behind. Either way it is kept and labelled, not dropped. A run stops early, and says so,
when more than 20% of submits fail or time out, or free memory drops below 200 MB.

## Definitions

- **Submit → verdict**: duration of `POST /api/submit`, which grades synchronously.
- **Server stages** (`LOADTEST_TIMING=1` only):
  - `slot_wait`: waiting for one of MAX_CONCURRENT_SUBMITS slots, plus the thread hop
  - `prep`: question lookup, attempt number, pre-check
  - one round trip per Judge0 call (3 per submission)
  - `classify`
  - `db_write`: SQLite insert
- **Visible after verdict**: time from a submission's verdict to the first lecturer
  submissions poll that contains it. This is bounded by the 3 s poll interval.
- **Discussion points ready**: the first `/api/lecturer/clusters` response that contains every
  student's latest submission and has a label on every wrong-answer group of 2+ students.
  This is reported relative to the last verdict and to time-up. Other clusters' labels are
  deterministic and can legitimately be empty.
- **LLM waste** (stub): HTTP calls compared with distinct prompts. Identical prompts re-sent
  while one is still in flight come from overlapping polls. Identical prompts re-sent after
  one finished mean the cache key changed but the snippets didn't.
