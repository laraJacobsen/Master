# Load test: calibrate, 1 student

> **NOT FOR REPORTING** — provisional: heavy apps open (Chrome, VS Code, claude-desktop); machine-bound / not for reporting; machine-bound: pre-run MemAvailable 1734 MB < 2048 MB; swap-in peaked at 4612 kB/s (5 s avg); calibration run (verdict reference, not a load result)

Judge0 1.13.1: COUNT=4 (4 worker processes), MAX_CONCURRENT_SUBMITS=16 — higher than the worker count, so submits queue inside Judge0. Question limits: CPU 5.0 s, memory 128000 kB, 3 tests/submission. LLM: stub (2.0 s fixed). Machine: Intel(R) Core(TM) i5-8265U CPU @ 1.60GHz, 4 cores / 8 threads, 7755 MB RAM (1734 MB available, 3923 MB swap used at start).

## Submit → verdict (s)

| n | p50 | p95 | p99 | max | errors | timeouts | verdict mismatches |
|---|---|---|---|---|---|---|---|
| 25 | 0.71 | 1.29 | 12.41 | 15.91 | 0 | 0 | 0 |

## Server-side stages (s, LOADTEST_TIMING)

| stage | p50 | p95 | max |
|---|---|---|---|
| slot_wait_s | 0.0004 | 0.0007 | 0.0008 |
| prep_s | 0.0018 | 0.0028 | 0.0031 |
| judge0_total_s | 0.7369 | 1.2276 | 15.8864 |
| classify_s | 0.0001 | 0.0007 | 0.0009 |
| db_write_s | 0.0036 | 0.0107 | 0.0889 |
| server_total_s | 0.7000 | 1.2881 | 15.8992 |
| client_minus_server_s | 0.0058 | 0.0096 | 0.0157 |
| one Judge0 call (n=63) | 0.2439 | 0.4870 | 5.3003 |

## Lecturer side

- Verdict → visible in submissions list: p50 1.44 s, p95 2.76 s, max 2.81 s (3 s poll interval)
- Dashboard reflects the batch with labels: 2.52 s after the last verdict
- Wrong-answer groups needing a label at the end: 0 (model: 0, fallback: 0)
- /api/lecturer/clusters: 17 polls, p50 0.04 s, p95 0.17 s, max 0.24 s; 0 started while an earlier one was still in flight (max 1 at once)
- Label calls (backend log): 0, used model 0
- LLM HTTP calls: 0 for 0 distinct prompts; identical prompt re-sent while one was in flight: 0, after one had finished: 0

## Machine

- Min MemAvailable 1474 MB, max swap-in 22648 kB/s, max swap-out 0 kB/s, mean CPU 26.3 %, backend RSS max 216 MB, client loop lag max 0.003 s
- Machine-bound: **yes** — pre-run MemAvailable 1734 MB < 2048 MB; swap-in peaked at 4612 kB/s (5 s avg); client-bound: no

## Targets

| check | result | value |
|---|---|---|
| error/timeout rate < 2% | PASS | 0.0% |
| no verdict mismatches | – | unchecked (no calibration) |
