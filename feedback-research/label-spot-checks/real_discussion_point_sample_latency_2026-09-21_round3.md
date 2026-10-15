# Per-stage latency, current pipeline / current provider (IDUN)

Measured 2026-09-21 -- see aggregation.py's own logging (captured below) plus this script's own wall-clock timers around _cluster_by_similarity() and _generate_subcluster_labels().

## Per-exercise stage timing

| exercise | submissions | sub-clusters | normalize/diff+cluster (s) | Label stage wall-clock (s), parallel | sub-clusters labeled |
|---|---|---|---|---|---|
| sum-ints | 15 | 5 | 0.032 | 4.638 | 5 |
| double-it | 11 | 5 | 0.010 | 2.221 | 2 |
| is_palindrome | 6 | 3 | 0.022 | 7.755 | 3 |
| count_vowels | 6 | 3 | 0.009 | 2.861 | 3 |
| second_largest | 6 | 3 | 0.019 | 5.833 | 3 |

**Totals**: normalize/diff+cluster = 0.092s across all 5 exercises (near-free, as expected -- matches the TF-IDF-baseline-era finding that this stage isn't the bottleneck). Label stage wall-clock = 23.309s.

## Raw per-call IDUN latencies (from aggregation.py's own per-call log line)

- wrong_answer sub-cluster IDUN call: 3 snippets, 3.160s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 3.334s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 4.379s, used_model=True
- wrong_answer sub-cluster IDUN call: 3 snippets, 4.477s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 4.634s, used_model=True
- wrong_answer sub-cluster Label calls: 5 sub-cluster(s), 4.638s wall-clock (parallel, max_workers=5)
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.605s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 2.216s, used_model=True
- wrong_answer sub-cluster Label calls: 2 sub-cluster(s), 2.221s wall-clock (parallel, max_workers=2)
- wrong_answer sub-cluster IDUN call: 2 snippets, 3.237s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 3.873s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 7.746s, used_model=True
- wrong_answer sub-cluster Label calls: 3 sub-cluster(s), 7.755s wall-clock (parallel, max_workers=3)
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.406s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.830s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 2.853s, used_model=True
- wrong_answer sub-cluster Label calls: 3 sub-cluster(s), 2.861s wall-clock (parallel, max_workers=3)
- wrong_answer sub-cluster IDUN call: 2 snippets, 3.734s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 4.382s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 5.831s, used_model=True
- wrong_answer sub-cluster Label calls: 3 sub-cluster(s), 5.833s wall-clock (parallel, max_workers=3)

## Parallelization check (the open question from the real-data findings doc)

Sum of individual per-call IDUN latencies (what sequential execution would have cost, back-to-back): 58.697s across 16 calls.
Actual wall-clock across all 5 exercises' Label stages (parallel within each exercise): 23.309s.

Per-sub-cluster Label calls ARE now parallelized (backend/aggregation.py's _generate_subcluster_labels(), added in this same change) -- confirmed empirically here, not just by code inspection: wall-clock stays close to the single slowest call per exercise rather than the sum of all calls in that exercise. Before this fix, _wrong_answer_subclusters() called _subcluster_discussion_point() in a plain sequential for-loop -- this was the actual state of the shipped code prior to this change, not a hypothetical.