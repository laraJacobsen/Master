# Per-stage latency, current pipeline / current provider (IDUN)

Measured 2026-09-21 -- see aggregation.py's own logging (captured below) plus this script's own wall-clock timers around _cluster_by_similarity() and _generate_subcluster_labels().

## Per-exercise stage timing

| exercise | submissions | sub-clusters | normalize/diff+cluster (s) | Label stage wall-clock (s), parallel | sub-clusters labeled |
|---|---|---|---|---|---|
| sum-ints | 15 | 5 | 0.020 | 3.500 | 5 |
| double-it | 11 | 5 | 0.014 | 1.311 | 2 |
| is_palindrome | 6 | 3 | 0.020 | 2.028 | 3 |
| count_vowels | 6 | 3 | 0.009 | 2.445 | 3 |
| second_largest | 6 | 3 | 0.020 | 3.048 | 3 |

**Totals**: normalize/diff+cluster = 0.084s across all 5 exercises (near-free, as expected -- matches the TF-IDF-baseline-era finding that this stage isn't the bottleneck). Label stage wall-clock = 12.330s.

## Raw per-call IDUN latencies (from aggregation.py's own per-call log line)

- wrong_answer sub-cluster IDUN call: 2 snippets, 1.755s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 2.060s, used_model=True
- wrong_answer sub-cluster IDUN call: 3 snippets, 2.418s, used_model=True
- wrong_answer sub-cluster IDUN call: 3 snippets, 2.555s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 3.495s, used_model=True
- wrong_answer sub-cluster Label calls: 5 sub-cluster(s), 3.499s wall-clock (parallel, max_workers=5)
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.000s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.306s, used_model=True
- wrong_answer sub-cluster Label calls: 2 sub-cluster(s), 1.310s wall-clock (parallel, max_workers=2)
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.494s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.809s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 2.013s, used_model=True
- wrong_answer sub-cluster Label calls: 3 sub-cluster(s), 2.027s wall-clock (parallel, max_workers=3)
- wrong_answer sub-cluster IDUN call: 2 snippets, 2.078s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 2.222s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 2.440s, used_model=True
- wrong_answer sub-cluster Label calls: 3 sub-cluster(s), 2.444s wall-clock (parallel, max_workers=3)
- wrong_answer sub-cluster IDUN call: 2 snippets, 2.193s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 2.738s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 3.033s, used_model=True
- wrong_answer sub-cluster Label calls: 3 sub-cluster(s), 3.048s wall-clock (parallel, max_workers=3)

## Parallelization check (the open question from the real-data findings doc)

Sum of individual per-call IDUN latencies (what sequential execution would have cost, back-to-back): 34.609s across 16 calls.
Actual wall-clock across all 5 exercises' Label stages (parallel within each exercise): 12.330s.

Per-sub-cluster Label calls ARE now parallelized (backend/aggregation.py's _generate_subcluster_labels(), added in this same change) -- confirmed empirically here, not just by code inspection: wall-clock stays close to the single slowest call per exercise rather than the sum of all calls in that exercise. Before this fix, _wrong_answer_subclusters() called _subcluster_discussion_point() in a plain sequential for-loop -- this was the actual state of the shipped code prior to this change, not a hypothetical.