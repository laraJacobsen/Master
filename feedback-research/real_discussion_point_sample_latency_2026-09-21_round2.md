# Per-stage latency, current pipeline / current provider (IDUN)

Measured 2026-09-21 -- see aggregation.py's own logging (captured below) plus this script's own wall-clock timers around _cluster_by_similarity() and _generate_subcluster_labels().

## Per-exercise stage timing

| exercise | submissions | sub-clusters | normalize/diff+cluster (s) | Label stage wall-clock (s), parallel | sub-clusters labeled |
|---|---|---|---|---|---|
| sum-ints | 15 | 5 | 0.016 | 4.767 | 5 |
| double-it | 11 | 5 | 0.018 | 2.029 | 2 |
| is_palindrome | 6 | 3 | 0.011 | 3.244 | 3 |
| count_vowels | 6 | 3 | 0.020 | 3.172 | 3 |
| second_largest | 6 | 3 | 0.022 | 3.737 | 3 |

**Totals**: normalize/diff+cluster = 0.087s across all 5 exercises (near-free, as expected -- matches the TF-IDF-baseline-era finding that this stage isn't the bottleneck). Label stage wall-clock = 16.949s.

## Raw per-call IDUN latencies (from aggregation.py's own per-call log line)

- wrong_answer sub-cluster IDUN call: 2 snippets, 2.915s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 2.975s, used_model=True
- wrong_answer sub-cluster IDUN call: 3 snippets, 3.500s, used_model=True
- wrong_answer sub-cluster IDUN call: 3 snippets, 4.158s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 4.756s, used_model=True
- wrong_answer sub-cluster Label calls: 5 sub-cluster(s), 4.767s wall-clock (parallel, max_workers=5)
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.203s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 2.024s, used_model=True
- wrong_answer sub-cluster Label calls: 2 sub-cluster(s), 2.028s wall-clock (parallel, max_workers=2)
- wrong_answer sub-cluster IDUN call: 2 snippets, 2.434s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 3.151s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 3.239s, used_model=True
- wrong_answer sub-cluster Label calls: 3 sub-cluster(s), 3.244s wall-clock (parallel, max_workers=3)
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.248s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.828s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 3.169s, used_model=True
- wrong_answer sub-cluster Label calls: 3 sub-cluster(s), 3.171s wall-clock (parallel, max_workers=3)
- wrong_answer sub-cluster IDUN call: 2 snippets, 3.220s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 3.522s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 3.730s, used_model=True
- wrong_answer sub-cluster Label calls: 3 sub-cluster(s), 3.737s wall-clock (parallel, max_workers=3)

## Parallelization check (the open question from the real-data findings doc)

Sum of individual per-call IDUN latencies (what sequential execution would have cost, back-to-back): 47.072s across 16 calls.
Actual wall-clock across all 5 exercises' Label stages (parallel within each exercise): 16.949s.

Per-sub-cluster Label calls ARE now parallelized (backend/aggregation.py's _generate_subcluster_labels(), added in this same change) -- confirmed empirically here, not just by code inspection: wall-clock stays close to the single slowest call per exercise rather than the sum of all calls in that exercise. Before this fix, _wrong_answer_subclusters() called _subcluster_discussion_point() in a plain sequential for-loop -- this was the actual state of the shipped code prior to this change, not a hypothetical.