# Discussion-point live verification findings (2026-09-16)

*Written by Claude Code after live-testing the wrong_answer sub-clustering pipeline
(`backend/aggregation.py`) against real Ollama output, prompted by a request to check
whether "the ollama thing discussion points are good." Two concrete, reproduced failure
modes were found, fixed, and re-verified in the same session. This doc exists so the
reasoning and the specific numbers behind each fix are traceable later, the same way
`pedagogical-feedback-design-decision.md`'s own "Runtime resource finding" section
works. Referenced by `discussion-point-spotcheck-2026-09-16.csv` (decision 3's
human/expert checkpoint, run against the pipeline after the fixes below landed).*

## What was tested

Real data already in `backend/prototype.db` (`karl`/`Jo` submitting literal `int` into
the student page while testing it) plus a deliberate set of 4 sum-ints `wrong_answer`
submissions with genuinely different bugs (adds 1 to the sum, drops the last number via
`nums[:-1]`, multiplies instead of summing, prints only the first number), run through
the live `/api/submit` → `/api/lecturer/clusters` pipeline with a real Ollama call
(`llama3.2:3b`, matching the runtime-resource finding above).

## Failure 1: over-merging, reproduced with clean data

All 4 deliberately-distinct bugs (plus the real "+1" bug already in the DB) landed in
**one cluster**, confirming the over-permissive-threshold finding in this file's parent
docstring, now with unambiguous ground truth (the bugs were chosen to be obviously
different, not organically ambiguous). The resulting discussion point then asserted a
specific claim ("off-by-one adjustment, iterating over indices one less than the
length") true of only 1 of the 5 merged snippets.

Root-caused to two independent problems, both in `_cluster_by_similarity()`:

- **`TfidfVectorizer`'s default `token_pattern` drops every operator, bracket, and
  digit.** Checked directly: canonicalizing the 4 bugs and vectorizing with defaults
  left a vocabulary of `['for', 'in', 'var1'..'var7']` -- the actual bug-distinguishing
  tokens (`+`, `-`, `*=`, `[`, `]`, `1`, `0`) were invisible before clustering even
  started. Fixed with `token_pattern=r"\S+"` (every canonicalized token is already
  space-joined by `_canonicalize()`, so this just stops discarding them). Re-measured
  pairwise cosine distances on the same 4 bugs: 0.098-0.240 between genuinely different
  bugs, 0.000 between two submissions of identical code -- a real gap to threshold on,
  which didn't exist before this fix regardless of what threshold was chosen.
- **`linkage="average"` chains distinct bugs together.** Even with the token-pattern fix
  and a retuned threshold (tried 0.15), 3 of the 4 bugs still merged: two bugs each
  moderately close to a third (the identical-code pair) got pulled together by average
  linkage's cluster-mean distance, despite their own direct pairwise distance being the
  largest in the group. Switched to `linkage="complete"` (merges on the *maximum*
  pairwise distance, not the mean), which doesn't chain the same way. At `complete`
  linkage, thresholds 0.05-0.09 all correctly separated the 3 distinct bugs into their
  own clusters while still merging the one genuinely-identical-code pair. Landed on
  0.05, the safer end of that range: a false split costs nothing (each row is still
  individually correct), a false merge produces an actively wrong claim to a lecturer.

**Fixed in `backend/aggregation.py`**: `_TOKEN_PATTERN = r"\S+"` passed to
`TfidfVectorizer`, `linkage="complete"`, `WRONG_ANSWER_SUBCLUSTER_DISTANCE` retuned
`0.4 → 0.05`. Re-verified against the same 5-submission check: clusters now match ground
truth exactly (2 identical-code submissions merge, 3 distinct bugs each stand alone).
Still one (question, sample) data point per the parent docstring's own caveat -- not
tuned against labeled data, and per-exercise tuning is still the eventual right move.

## Failure 2: fabrication on degenerate input (new, worse than over-generalization)

Separately, the two real `karl`/`Jo` submissions (`int\n`, unrelated to any real
attempt -- canonicalizes to the single token `VAR1`) produced:

> "All code snippets contain an identical addition of 1 to the result of VAR2\*VAR2"

There is no `VAR2`, no multiplication, and no addition anywhere in the actual input.
This is a direct violation of the model's own system-prompt instruction ("if the
snippets don't share an obvious concrete pattern, say plainly that they don't rather
than inventing one") -- and `_call_ollama_subcluster_pattern()`'s validation only
checked for non-empty output and no second-person phrasing, nothing that could catch an
ungrounded claim.

**Fixed**: `_MIN_TOKENS_FOR_PATTERN_CALL = 4` -- below this many canonicalized tokens in
any representative snippet, `_subcluster_discussion_point()` skips the Ollama call
entirely and uses the generic curated fallback line, rather than trust the model to
self-police on degenerate input. Re-verified: the same `karl`/`Jo` pair now produces the
generic "Wrong answer -- worth tracing through the test input..." line instead of a
fabricated claim.

This guards the specific case observed (a canonicalized snippet with almost nothing in
it). It is not a general fix for the model asserting ungrounded claims on richer input --
the spot-check batch below found more of exactly that (see rows 2, 15, 16 in
`discussion-point-spotcheck-2026-09-16.csv`: a false "negative step size" claim on code
with no step argument at all, and two false "mismatched/missing parenthesis" claims on
syntactically valid code).

## What this does and doesn't establish

Both fixes are verified against the project's own `smoke_test.py` (all tests pass,
including "wrong_answer sub-clustering separates two bug shapes") and against fresh live
data. They remove two concrete, reproduced failure modes -- they do not establish that
the pipeline is validated. Per `pedagogical-feedback-design-decision.md` decision 3, the
next step was always the human/expert spot-check pass, not further automated tuning;
`discussion-point-spotcheck-2026-09-16.csv` is that pass's input batch, generated by
running the fixed pipeline for real (not hand-written), across a spread of
exec_verdict/error_type categories and cluster sizes. Nothing was retuned based on that
batch -- what to change next depends on how it's rated.
