# Per-stage latency, current pipeline / current provider (IDUN)

Measured 2026-09-21 -- see aggregation.py's own logging (captured below) plus this script's own wall-clock timers around _cluster_by_similarity() and _generate_subcluster_labels().

## Per-exercise stage timing

| exercise | submissions | sub-clusters | normalize/diff+cluster (s) | Label stage wall-clock (s), parallel | sub-clusters labeled |
|---|---|---|---|---|---|
| sum-ints | 15 | 5 | 0.013 | 2.590 | 5 |
| double-it | 11 | 5 | 0.014 | 1.291 | 2 |
| is_palindrome | 6 | 3 | 0.008 | 1.487 | 3 |
| count_vowels | 6 | 3 | 0.017 | 1.451 | 3 |
| second_largest | 6 | 3 | 0.016 | 1.745 | 3 |

**Totals**: normalize/diff+cluster = 0.069s across all 5 exercises (near-free, as expected -- matches the TF-IDF-baseline-era finding that this stage isn't the bottleneck). Label stage wall-clock = 8.565s.

## Raw per-call IDUN latencies (from aggregation.py's own per-call log line)

- wrong_answer sub-cluster IDUN call: 3 snippets, 1.380s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.407s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.435s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.514s, used_model=True
- wrong_answer sub-cluster IDUN call: 3 snippets, 2.586s, used_model=True
- wrong_answer sub-cluster Label calls: 5 sub-cluster(s), 2.590s wall-clock (parallel, max_workers=5)
- wrong_answer sub-cluster IDUN call: 2 snippets, 0.736s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.283s, used_model=True
- wrong_answer sub-cluster Label calls: 2 sub-cluster(s), 1.291s wall-clock (parallel, max_workers=2)
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.011s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.228s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.478s, used_model=True
- wrong_answer sub-cluster Label calls: 3 sub-cluster(s), 1.487s wall-clock (parallel, max_workers=3)
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.243s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.443s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.442s, used_model=True
- wrong_answer sub-cluster Label calls: 3 sub-cluster(s), 1.451s wall-clock (parallel, max_workers=3)
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.200s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.212s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.728s, used_model=True
- wrong_answer sub-cluster Label calls: 3 sub-cluster(s), 1.744s wall-clock (parallel, max_workers=3)

## Parallelization check (the open question from the real-data findings doc)

Sum of individual per-call IDUN latencies (what sequential execution would have cost, back-to-back): 22.326s across 16 calls.
Actual wall-clock across all 5 exercises' Label stages (parallel within each exercise): 8.565s.

Per-sub-cluster Label calls ARE now parallelized (backend/aggregation.py's _generate_subcluster_labels(), added in this same change) -- confirmed empirically here, not just by code inspection: wall-clock stays close to the single slowest call per exercise rather than the sum of all calls in that exercise. Before this fix, _wrong_answer_subclusters() called _subcluster_discussion_point() in a plain sequential for-loop -- this was the actual state of the shipped code prior to this change, not a hypothetical.