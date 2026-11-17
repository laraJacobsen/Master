# Per-stage latency, current pipeline / current provider (IDUN)

Measured 2026-09-21 -- see aggregation.py's own logging (captured below) plus this script's own wall-clock timers around _group_wrong_answers() and _generate_subcluster_labels().

## Per-exercise stage timing

| exercise | submissions | sub-clusters | normalize/diff+cluster (s) | Label stage wall-clock (s), parallel | sub-clusters labeled |
|---|---|---|---|---|---|
| sum-ints | 15 | 6 | 0.001 | 2.217 | 5 |
| double-it | 11 | 3 | 0.001 | 1.445 | 2 |
| is_palindrome | 6 | 3 | 0.030 | 1.324 | 3 |
| count_vowels | 6 | 3 | 0.024 | 1.611 | 3 |
| second_largest | 6 | 3 | 0.015 | 1.881 | 3 |

**Totals**: normalize/diff+cluster = 0.071s across all 5 exercises (near-free, as expected -- matches the TF-IDF-baseline-era finding that this stage isn't the bottleneck). Label stage wall-clock = 8.478s.

## Raw per-call IDUN latencies (from aggregation.py's own per-call log line)

- wrong_answer diff+cluster: question=sum-ints, 0 of 15 submissions diff-clustered -> 6 groups total, 0.000s
- wrong_answer sub-cluster LLM call (idun): 3 snippets, 1.389s, used_model=True
- wrong_answer sub-cluster LLM call (idun): 3 snippets, 1.597s, used_model=True
- wrong_answer sub-cluster LLM call (idun): 2 snippets, 1.610s, used_model=True
- wrong_answer sub-cluster LLM call (idun): 2 snippets, 2.003s, used_model=True
- wrong_answer sub-cluster LLM call (idun): 2 snippets, 2.206s, used_model=True
- wrong_answer sub-cluster Label calls: 5 sub-cluster(s), 2.217s wall-clock (parallel, max_workers=5)
- wrong_answer diff+cluster: question=double-it, 1 of 11 submissions diff-clustered -> 3 groups total, 0.000s
- wrong_answer sub-cluster LLM call (idun): 2 snippets, 1.080s, used_model=True
- wrong_answer sub-cluster LLM call (idun): 2 snippets, 1.437s, used_model=True
- wrong_answer sub-cluster Label calls: 2 sub-cluster(s), 1.444s wall-clock (parallel, max_workers=2)
- wrong_answer diff+cluster: question=is_palindrome, 6 of 6 submissions diff-clustered -> 3 groups total, 0.030s
- wrong_answer sub-cluster LLM call (idun): 2 snippets, 1.172s, used_model=True
- wrong_answer sub-cluster LLM call (idun): 2 snippets, 1.232s, used_model=True
- wrong_answer sub-cluster LLM call (idun): 2 snippets, 1.316s, used_model=True
- wrong_answer sub-cluster Label calls: 3 sub-cluster(s), 1.324s wall-clock (parallel, max_workers=3)
- wrong_answer diff+cluster: question=count_vowels, 6 of 6 submissions diff-clustered -> 3 groups total, 0.023s
- wrong_answer sub-cluster LLM call (idun): 2 snippets, 1.194s, used_model=True
- wrong_answer sub-cluster LLM call (idun): 2 snippets, 1.343s, used_model=True
- wrong_answer sub-cluster LLM call (idun): 2 snippets, 1.608s, used_model=True
- wrong_answer sub-cluster Label calls: 3 sub-cluster(s), 1.611s wall-clock (parallel, max_workers=3)
- wrong_answer diff+cluster: question=second_largest, 6 of 6 submissions diff-clustered -> 3 groups total, 0.015s
- wrong_answer sub-cluster LLM call (idun): 2 snippets, 1.520s, used_model=True
- wrong_answer sub-cluster LLM call (idun): 2 snippets, 1.528s, used_model=True
- wrong_answer sub-cluster LLM call (idun): 2 snippets, 1.873s, used_model=True
- wrong_answer sub-cluster Label calls: 3 sub-cluster(s), 1.881s wall-clock (parallel, max_workers=3)

## Parallelization check (the open question from the real-data findings doc)

Sum of individual per-call IDUN latencies (what sequential execution would have cost, back-to-back): 24.108s across 16 calls.
Actual wall-clock across all 5 exercises' Label stages (parallel within each exercise): 8.478s.

Per-sub-cluster Label calls ARE now parallelized (backend/aggregation.py's _generate_subcluster_labels(), added in this same change) -- confirmed empirically here, not just by code inspection: wall-clock stays close to the single slowest call per exercise rather than the sum of all calls in that exercise. Before this fix, _wrong_answer_subclusters() called _subcluster_discussion_point() in a plain sequential for-loop -- this was the actual state of the shipped code prior to this change, not a hypothetical.