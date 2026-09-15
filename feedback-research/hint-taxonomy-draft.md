# Hint taxonomy draft: safe scaffolds vs. answer-giving

Step 1 of the plan in `pedagogical-feedback-design-decision.md`. Draft only — not wired into
`classify.py` yet. Worked against real cases from `corpus.py` so the tiers aren't abstract.

## The scale

Borrows the standard ITS (intelligent tutoring system) hint-sequence idea — hints escalate from
"something's wrong, here's where" up to "here's the fix" — and draws the allowed/disallowed line
explicitly, since that line is the actual design constraint from the supervisor meeting.

| Tier | Name | What it gives the student | Default policy |
|---|---|---|---|
| 1 | **Locate** | Which verdict category, and where (line/function), no diagnosis | Always safe |
| 2 | **Name** | Names the *kind* of problem (error type, or "output doesn't match on this input") without saying why | Safe |
| 3 | **Direct** | Points at the specific concept/operation at fault, phrased as a question or a thing to check — not the fix | Safe, this is the ceiling for default output |
| 4 | **Bottom-out** | States the corrected code or the exact fix | Disallowed in the shipped tool — reserved as a deliberate contrast condition for evaluation only (e.g. an "answer-giving" arm to compare against in the classroom pilot) |

Tiers 1–3 is what `classify.py`'s output would drive by default. Tier 4 exists in the taxonomy
because having it named and written down is what makes "does this cross the line" checkable during
the expert spot-check step later — reviewers rate each generated hint against tier 1–4, and
anything landing at 4 is a failure, not silently dropped.

## Escalation model

Tier is driven by `attempt_number` (already tracked for resubmissions), not an explicit
"give me another hint" request from the student:

```
tier = min(attempt_number, per_verdict_ceiling(verdict))
```

So a student's first submission that fails gets tier 1, their second attempt at the same problem
gets tier 2, and so on — no UI needed for a student to ask for more help, which also sidesteps the
question of whether asking for hints should feel like "giving up."

Two ceilings apply, and they're not the same number:

- **Structural ceiling** (per verdict) — how many of the 4 tiers actually contain distinct,
  meaningful content for that verdict category. See table below.
- **Shipped policy cap = 3** — tier 4 (bottom-out) is never shown to a student regardless of
  structural ceiling, per the earlier default policy. A verdict with a structural ceiling of 4
  still only ever surfaces up to tier 3 in the live tool; tier 4 is measured (see eval section) but
  not shipped.

**Instructor-level override** (letting an instructor raise/lower the ceiling, or unlock tier 4 for
their own section) is left as a seam for later — worth designing the ceiling lookup as a small
per-verdict table/function now so an override layer can wrap it later, but not building the
override itself yet.

### Structural ceiling by verdict

| Verdict / error_type | Structural ceiling | Why |
|---|---|---|
| `syntax_error` / `indentation_error` | 2 | Tier 3 collapses into tier 2 — see "doesn't fit cleanly" below |
| `function_not_found` | 2 | Same collapse — naming the expected name basically *is* tier 2 |
| `wrong_answer` | 4 | Full scale — see 03, 04, 05 examples |
| `runtime_error` (NameError, TypeError, IndexError, AttributeError, RecursionError, KeyError, EOFError, ModuleNotFoundError) | 4 | Full scale — see 08, 09, 10, 11, 12, 24, 25 examples |
| `timeout` / `oom` / `output_limit_exceeded` | 4, drafted as one shared "bounded-loop bug" hint family rather than three independent ones (split back out only if simulated-student fix-rates diverge) — see below | |
| `rejected` | 1 | Format message only, no tiering |

## Worked examples against corpus.py cases

**`03_wrong_case_sensitive`** (wrong_answer — forgot `.lower()`)
- Tier 1: "Your output didn't match on the test input for this problem."
- Tier 2: "The mismatch happens on how the input's letters are compared, not on the overall logic."
- Tier 3: "Case — capital vs. lowercase letters — check whether your comparison treats `'R'` and
  `'r'` as the same character."
- Tier 4 (excluded): "Add `.lower()` before comparing." ← this is the line we don't cross.

**`05_wrong_off_by_one`** (wrong_answer — off-by-one index)
- Tier 1: "Wrong answer on the test input."
- Tier 2: "It's failing partway through the comparison loop, not on the whole-string check."
- Tier 3: "Trace `i` and the index it's compared against by hand for a 4-character string — do
  they meet in the middle the way you expect?"
- Tier 4 (excluded): "Change `n - i - 2` to `n - i - 1`."

**`08_name_error`** (runtime_error / NameError)
- Tier 1: "Your program crashed before producing output."
- Tier 2: "NameError — Python doesn't recognize a name you used."
- Tier 3: "Read the last line of the traceback: which name is it saying isn't defined? Is that
  a function you meant to write, or a typo for one you did write?"
- Tier 4 (excluded): "You called `normalize()` but never defined it — use your own function
  instead."

**`11_attribute_error`** (runtime_error / AttributeError — typo'd method name)
- Tier 1: "Your program crashed before producing output."
- Tier 2: "AttributeError — you called a method that doesn't exist on that object."
- Tier 3: "Check the exact spelling of the method name against Python's string methods —
  is it spelled exactly the way you'd find it in the docs?"
- Tier 4 (excluded): "`.lowerr()` should be `.lower()`."

**`12_recursion_error`** (runtime_error / RecursionError — no base case)
- Tier 1: "Your program crashed before producing output."
- Tier 2: "RecursionError — your function called itself too many times without stopping."
- Tier 3: "What condition should make your function return *without* calling itself again? Does
  your function currently have one?"
- Tier 4 (excluded): "Add a base case that returns when the string has length ≤ 1."

**`14_function_not_found`** (wrong function name entirely)
- Tier 1: "The grader couldn't find the function it expected to call."
- Tier 2: "The function name it's looking for is `is_palindrome` — check what you named yours."
- Tier 3 here basically collapses into tier 2 — there's very little room between "name what's
  expected" and "tell them to rename it," which is itself worth flagging (see open question below).

**`15_timeout_missing_increment`** (timeout — infinite loop, forgot to increment)
- Tier 1: "Your program didn't finish in time."
- Tier 2: "It looks like it's stuck in a loop that never ends."
- Tier 3: "Look at the variable your `while` condition depends on — does anything inside the loop
  body actually change it?"
- Tier 4 (excluded): "Add `i += 1` inside the loop."

**`24_disallowed_import`** (ModuleNotFoundError — numpy)
- Tier 1: "Your program crashed before producing output."
- Tier 2: "ModuleNotFoundError — you imported something that isn't available."
- Tier 3: "This exercise only needs the standard string operations covered in lecture — do you
  need that import at all?"
- Tier 4 (excluded): "Remove the numpy import, you don't need it."

## Cases the tier scale doesn't fit cleanly

- **`syntax_error`/`indentation_error`** (06, 07): there's often no "concept" to point at short of
  the fix itself (a missing colon *is* the bug). Tier 3 probably has to stay meta: "compare this
  line to the syntax pattern from the lecture slides for defining a function" rather than pointing
  at the missing character — but this is the weakest-feeling tier 3 in the set and worth
  scrutinizing in the expert checkpoint.
- **`oom`/`output_limit_exceeded`** (16, 18, 19): tier 3 can name the mechanism ("your loop keeps
  allocating memory/printing and never stops") but for a first-week intro exercise there may not be
  a subtler concept beyond "find the loop that doesn't terminate," which overlaps heavily with the
  `timeout` case. Possibly these three verdicts should share one hint family (bounded-loop bugs)
  rather than three separate ones.
- **`rejected`** (20, 21, 22 — empty/oversized submission): not really a "hint" case at all, this is
  closer to a format-validation message ("your submission is empty" / "over the size limit") with
  no tier structure needed.

## Simulated-student eval: scoring plan

Score fix-success **per (verdict, tier)** cell, up to each verdict's *structural* ceiling —
including tier 4, even though tier 4 never ships. Two things this buys:

- **Empirical check on the structural ceilings above.** If tier 2 → tier 3 shows no fix-rate lift
  for a verdict currently marked ceiling-4, that's evidence to shrink its ceiling, not just a
  guess from the worked examples.
- **Empirical check on the escalation rate itself.** Plotting fix-rate against tier per verdict
  shows where the curve flattens — that's the signal for whether `attempt_number` should map to
  tier 1:1, or escalate faster/slower per verdict.

Treat all of this as **relative signal** (shape of the curve, where it flattens) rather than an
absolute fix-rate number — the simulated-student blind spot (an LLM playing a novice doesn't fail
the way a real beginner does) still applies here, same as it does to the top-line eval. That's
exactly what the human/expert spot-check checkpoint is for: confirming the curve's shape holds up
against real judgment, not just replacing it.

## Resolved

- ~~Fixed tier vs. student-requested escalation~~ → resolved: `attempt_number`-driven, no explicit
  request. See "Escalation model" above.
- ~~Uniform 4-tier scale for every verdict~~ → resolved: tier *definitions* stay uniform, but
  *ceiling* varies by verdict. See "Structural ceiling by verdict" above.
- ~~Score fix-success per tier~~ → resolved: yes, per (verdict, tier), treated as relative signal.
  See "Simulated-student eval: scoring plan" above.

## Open questions still remaining

1. Instructor-level override of the ceiling (and whether to ever unlock tier 4 for a given section)
   is deliberately deferred — the ceiling lookup should be written as a small per-verdict
   table/function now so an override layer can wrap it later without a rewrite.
2. ~~Does `attempt_number` reset per problem~~ → resolved: `attempt_number` is scoped to
   `(student_token, question_id)`, not to the student or session as a whole. Moving to a new
   problem always starts at `attempt_number = 1` / tier 1, regardless of attempt count on any
   other problem. So the per-verdict ceiling table only ever needs to reason about one problem's
   history at a time — no cross-problem state to track.
3. `timeout` / `oom` / `output_limit_exceeded` will be drafted as **one shared hint family** (agreed
   — bounded-loop-bug framing covers all three at the tier-1–3 level). Still split back out later
   if the simulated-student fix-rates diverge meaningfully across the three verdicts despite the
   shared content — that check happens naturally once the (verdict, tier) scoring pass runs.
4. **New finding (2026-09-15, first `simulated_student_eval.py` run against `llama3.2:1b`):**
   nearly every ceiling-4 runtime_error verdict hit 100% fix-rate at tier 1 already — the vaguest
   hint in the whole scale ("your program crashed before producing output"). That's not strong
   evidence the tiers themselves are redundant; it's more likely that `is_palindrome` is too easy a
   benchmark to discriminate hint tiers with *any* model, even a small one — an 8-line program with
   a one-line bug is often fixable from the original code alone once a model is told "something's
   wrong," regardless of how much more the hint says. This sharpens (and raises the priority of) the
   open question above about growing the corpus to more exercises: the current 25-case,
   single-exercise corpus may not be able to produce a trustworthy tier-discrimination signal no
   matter how much the model or sampling improves, because the *problems* aren't hard enough for the
   tiers to matter. Worth prioritizing a second, harder exercise before drawing any real conclusions
   from fix-rate curves. (Separately: per-cell results also turned out to be non-deterministic
   run-to-run at n=1 — see `simulated_student_eval.py`'s docstring for that limitation and the
   repeat-sampling fix.)
5. **Does re-showing all prior tiers at each escalation step make sense for a real student, not just
   for the simulated eval?** (2026-09-15, k=3 repeat-sampled run against `llama3.2:1b`.) Nearly
   every ceiling-4 verdict's fix-rate flattened or *declined* from tier 2 onward — e.g.
   ModuleNotFoundError went 100% → 100% → 67% → 33%, monotonically worse as the hint got more
   explicit, which is backwards from what hint content alone should ever produce. The escalation
   model (see above) currently shows tier N as tiers 1..N concatenated — at tier 4 the student sees
   four stacked hint lines at once. The immediate suspect is `llama3.2:1b` specifically choking on
   longer, denser prompts (a small-model artifact, not informative about hint quality) — an ablation
   run with hints shown singly instead of cumulatively (`CUMULATIVE_HINTS=False`) is queued to check
   this. **But even if the ablation confirms it's mostly a small-model confound, the underlying
   design question is real and separate from that confound**: is re-showing every earlier hint on
   each resubmission actually the right choice for a real student, or does it risk the same kind of
   overload in a human that we're seeing in this model — i.e. would a student on their 4th attempt
   be better served by *just* the newest, most specific hint than by rereading three earlier ones
   first? Not decided either way yet; needs its own answer independent of what the ablation shows.

   **Ablation result (2026-09-15, `CUMULATIVE_HINTS=False`, same k=3, same 210 trials):** the
   picture is partial, not a clean confirmation. First, a calibration point the ablation exposed:
   tier 1's prompt is byte-identical under both conditions (cumulative-up-to-1 is just hint 1
   alone), so the two runs' tier-1 numbers are two samples of the *same* underlying distribution —
   and they still swung by 30-67 percentage points on several verdicts (timeout: 0%→67%, KeyError:
   33%→67%, RecursionError: 67%→33%). That's the real noise floor at k=3, and it's large — most of
   the tier-to-tier deltas seen in either single run are smaller than this floor and shouldn't be
   read as signal at all. Against that floor, tier 2 and tier 3 show no consistent direction
   (roughly as many verdicts improved without cumulative stacking as got worse). **Tier 4 is the one
   place a consistent pattern survives the noise floor**: across every verdict, the cumulative run
   was never better than the non-cumulative one at tier 4 (tied on 8 of 12 comparable verdicts,
   clearly worse on the rest — output_limit_exceeded 0% vs. 67%, AttributeError 67% vs. 100%,
   wrong_answer 56% vs. 78%, oom 0% vs. 17%). So: some real support for "stacking specifically hurts
   at the longest/most-tier-4 prompt," but not strong enough, given the demonstrated noise floor, to
   treat as settled — would need a larger k (or a non-LLM-based check) before trusting it enough to
   change the escalation model. The real-student version of the question (item 5's actual title) is
   still completely open regardless of how this resolves.
