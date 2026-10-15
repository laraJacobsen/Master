# Per-stage latency, current pipeline / current provider (IDUN)

Measured 2026-09-21 -- see aggregation.py's own logging (captured below) plus this script's own wall-clock timers around _group_wrong_answers() and _generate_subcluster_labels().

## Per-exercise stage timing

| exercise | submissions | sub-clusters | normalize/diff+cluster (s) | Label stage wall-clock (s), parallel | sub-clusters labeled |
|---|---|---|---|---|---|
| sum-ints | 15 | 6 | 0.001 | 1.983 | 5 |
| double-it | 11 | 3 | 0.001 | 1.277 | 2 |
| is_palindrome | 6 | 3 | 0.035 | 2.011 | 3 |
| count_vowels | 6 | 3 | 0.028 | 1.601 | 3 |
| second_largest | 6 | 3 | 0.027 | 1.816 | 3 |

**Totals**: normalize/diff+cluster = 0.091s across all 5 exercises (near-free, as expected -- matches the TF-IDF-baseline-era finding that this stage isn't the bottleneck). Label stage wall-clock = 8.687s.

## Raw per-call IDUN latencies (from aggregation.py's own per-call log line)

- wrong_answer diff+cluster: question=sum-ints, 0 of 15 submissions diff-clustered -> 6 groups total, 0.000s
- wrong_answer sub-cluster IDUN call: 3 snippets, 1.331s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.435s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.813s, used_model=True
- wrong_answer sub-cluster IDUN call: 3 snippets, 1.880s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.971s, used_model=True
- wrong_answer sub-cluster Label calls: 5 sub-cluster(s), 1.983s wall-clock (parallel, max_workers=5)
- wrong_answer diff+cluster: question=double-it, 1 of 11 submissions diff-clustered -> 3 groups total, 0.000s
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.065s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.270s, used_model=True
- wrong_answer sub-cluster Label calls: 2 sub-cluster(s), 1.276s wall-clock (parallel, max_workers=2)
- wrong_answer diff+cluster: question=is_palindrome, 6 of 6 submissions diff-clustered -> 3 groups total, 0.035s
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.146s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.511s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.999s, used_model=True
- wrong_answer sub-cluster Label calls: 3 sub-cluster(s), 2.010s wall-clock (parallel, max_workers=3)
- wrong_answer diff+cluster: question=count_vowels, 6 of 6 submissions diff-clustered -> 3 groups total, 0.027s
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.335s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.363s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.593s, used_model=True
- wrong_answer sub-cluster Label calls: 3 sub-cluster(s), 1.600s wall-clock (parallel, max_workers=3)
- wrong_answer diff+cluster: question=second_largest, 6 of 6 submissions diff-clustered -> 3 groups total, 0.026s
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.599s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.653s, used_model=True
- wrong_answer sub-cluster IDUN call: 2 snippets, 1.810s, used_model=True
- wrong_answer sub-cluster Label calls: 3 sub-cluster(s), 1.816s wall-clock (parallel, max_workers=3)

## Parallelization check (the open question from the real-data findings doc)

Sum of individual per-call IDUN latencies (what sequential execution would have cost, back-to-back): 24.774s across 16 calls.
Actual wall-clock across all 5 exercises' Label stages (parallel within each exercise): 8.687s.

Per-sub-cluster Label calls ARE now parallelized (backend/aggregation.py's _generate_subcluster_labels(), added in this same change) -- confirmed empirically here, not just by code inspection: wall-clock stays close to the single slowest call per exercise rather than the sum of all calls in that exercise. Before this fix, _wrong_answer_subclusters() called _subcluster_discussion_point() in a plain sequential for-loop -- this was the actual state of the shipped code prior to this change, not a hypothetical.