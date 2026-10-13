# Shape-vs-behavior limitation in wrong_answer sub-clustering (2026-09-21)

*Written by Claude Code while evaluating the diff-against-reference sub-clustering
signal (see `backend/aggregation.py`'s 2026-09-21 docstring entry, `subcluster_eval.py`,
and `run_diff_baseline.py`) against the hand-labeled ground truth in
`subcluster_ground_truth_sample.csv`. Documents a real, reproduced case that no
code-based clustering signal tested so far can close, and why closing it needs a
different kind of signal entirely. This is a scoped methodological limitation, not an
open bug to keep chasing with the current representation.*

## The case

Four `double-it` wrong_answer submissions in the ground truth (`DI-01`, `DI-02`,
`DI-05`, `DI-07` — hand-labeled `prints-twice`, since a human labeler comparing their
*output* naturally puts them in one group) produce **identical output** against every
sample input in the reading-aid table (`44`, `33`, `1010` for inputs `4`, `3`, `10`,
against a correct `8`, `6`, `20`), but reach it via three structurally different edits
relative to the reference solution `print(int(input()) * 2)`:

| id(s) | code | what actually happened |
|---|---|---|
| DI-01, DI-02 | `int = input()`<br>`print(int*2)` | shadows the builtin `int` with a variable holding the raw string; `int()` is never called at all |
| DI-05 | `print(input()*2)` | same root cause (no conversion), written inline with no intermediate variable |
| DI-07 | `print(int(input()*2))` | *does* call `int()` — just after the string was already doubled, not before |

`input()` returns a string; string `* 2` repeats it (`"4" * 2 == "44"`) rather than
multiplying the number. All three land on the same wrong output because `int("44")`
prints identically to the string `"44"` — the coincidence is in how Python renders the
result, not in the students' code.

## Why neither clustering signal groups these together

Both signals tested against this ground truth (`run_tfidf_baseline.py`'s raw-code
TF-IDF and `run_diff_baseline.py`'s diff-against-reference, now production — see
`backend/aggregation.py`) represent a submission by **what is different about its
code**, one against its own raw canonicalized text, the other against its diff from
the reference solution. On this case, that is exactly the correct behavior: DI-01/02
delete the `int(...)` call from the reference entirely, DI-05 does the same by a
different route, and DI-07 keeps `int(...)` but wraps the wrong span. Those are three
genuinely different code-level edits. Diff-against-reference (the current production
signal) never reaches the ground truth's 3 predicted groups for `double-it` in the
threshold sweep — it tops out at 4, because it's correctly telling DI-07 apart from
DI-01/02/05 at every threshold tested. See `run_diff_baseline.py`'s results table:
`double-it` ARI plateaus around 0.80–0.88, never 1.0, specifically because of this
group.

This is not a threshold problem and not fixable by trying a third code-similarity
signal (line-variance weighting, a different diff granularity, etc.) either — any
representation built from the submission's *text* is, by construction, measuring code
shape. These four submissions don't share a code shape. They share an output. A
signal that only ever looks at code can be correct or incorrect about code-shape
similarity, but it has no way to know two different shapes happen to behave the same
without running them.

## What would actually close it

An output/behavior-based signal: running each submission against the exercise's
sample inputs (exactly what `subcluster_ground_truth_io_table.md`'s reading aid
already does by hand) and using the resulting output vectors — or agreement/
disagreement with each other's outputs — as part of the clustering representation,
instead of or alongside the code-text representation. That's a different kind of
signal from everything evaluated so far (both are static/textual), with its own new
costs (running arbitrary student code for every cluster instead of just diffing
text) and its own new failure mode (two submissions that are wrong for unrelated
reasons but coincidentally agree on the sample inputs shown — the inverse of this
problem). Out of scope for this round; noted here so it doesn't get rediscovered
as a surprise later.

## Takeaway

Worth stating as a general result, not just a `double-it` quirk: **any
text/code-based clustering signal has a structural ceiling — it cannot correctly
group submissions whose behavioral agreement doesn't correspond to a shared
code-level pattern.** Diff-against-reference measurably narrowed that ceiling
(mean ARI 0.579 → 0.899 at the production threshold, `is_palindrome` 0.000 → 1.000 —
see `backend/aggregation.py`'s 2026-09-21 docstring entry), but it moved *along* the
code-similarity axis, not off it. That's a legitimate methodological finding about
the limits of code-similarity-based feedback clustering in general, independent of
which specific signal is used — worth stating as such rather than treated as
something the next signal tweak should be expected to fix.
