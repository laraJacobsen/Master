# Load test: single, 1 student

> **NOT FOR REPORTING** — provisional: heavy apps open (Chrome, VS Code, claude-desktop); machine-bound / not for reporting; machine-bound: pre-run MemAvailable 1855 MB < 2048 MB; swap-in peaked at 1369 kB/s (5 s avg)

Judge0 1.13.1: COUNT=4 (4 worker processes), MAX_CONCURRENT_SUBMITS=16 — higher than the worker count, so submits queue inside Judge0. Question limits: CPU 5.0 s, memory 128000 kB, 3 tests/submission. LLM: stub (2.0 s fixed). Machine: Intel(R) Core(TM) i5-8265U CPU @ 1.60GHz, 4 cores / 8 threads, 7755 MB RAM (1855 MB available, 3930 MB swap used at start).

## Submit → verdict (s)

| n | p50 | p95 | p99 | max | errors | timeouts | verdict mismatches |
|---|---|---|---|---|---|---|---|
| 1 | 0.71 | 0.71 | 0.71 | 0.71 | 0 | 0 | 0 |

## Server-side stages (s, LOADTEST_TIMING)

| stage | p50 | p95 | max |
|---|---|---|---|
| slot_wait_s | 0.0013 | 0.0013 | 0.0013 |
| prep_s | 0.0025 | 0.0025 | 0.0025 |
| judge0_total_s | 0.6921 | 0.6921 | 0.6921 |
| classify_s | 0.0006 | 0.0006 | 0.0006 |
| db_write_s | 0.0032 | 0.0032 | 0.0032 |
| server_total_s | 0.7001 | 0.7001 | 0.7001 |
| client_minus_server_s | 0.0100 | 0.0100 | 0.0100 |
| one Judge0 call (n=3) | 0.2351 | 0.2381 | 0.2384 |

## Lecturer side

- Verdict → visible in submissions list: p50 2.48 s, p95 2.48 s, max 2.48 s (3 s poll interval)
- Dashboard reflects the batch with labels: 2.47 s after the last verdict
- Wrong-answer groups needing a label at the end: 0 (model: 0, fallback: 0)
- /api/lecturer/clusters: 6 polls, p50 0.02 s, p95 0.03 s, max 0.03 s; 0 started while an earlier one was still in flight (max 1 at once)
- Label calls (backend log): 0, used model 0
- LLM HTTP calls: 0 for 0 distinct prompts; identical prompt re-sent while one was in flight: 0, after one had finished: 0

## Machine

- Min MemAvailable 1722 MB, max swap-in 4652 kB/s, max swap-out 0 kB/s, mean CPU 19.0 %, backend RSS max 163 MB, client loop lag max 0.003 s
- Machine-bound: **yes** — pre-run MemAvailable 1855 MB < 2048 MB; swap-in peaked at 1369 kB/s (5 s avg); client-bound: no

## Targets

| check | result | value |
|---|---|---|
| error/timeout rate < 2% | PASS | 0.0% |
| no verdict mismatches | – | unchecked (no calibration) |
