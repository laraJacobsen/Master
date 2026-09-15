# Pedagogical feedback layer: scoping decision (2026-09-15)

*Written after Claude Code (working in this repo) asked how to approach pedagogical feedback
quality, proposing a verdict → feedback-message layer on top of `classify.py` plus a
simulated-student eval loop before a real classroom pilot. Captures the answer given back to it,
since this is a net-new design area with no earlier work to point to. Updated same day with
answers to Claude Code's follow-up questions on hint escalation tiers, once it started drafting
the taxonomy.*

## Context

The 2026-09-15 supervisor meeting flagged a real constraint that hadn't been designed yet: feedback
"must not be a shortcut to the answer," which needs an actual taxonomy of safe hint types (e.g.
"re-read the problem statement," "what's the first test case checking?") versus hints that cross
into solving it for the student. That was filed as its own next-step item ("draft a hint taxonomy
for idle-student nudges, safe vs. answer-giving") separately from the feedback-quality question
Claude Code raised. There was no prior feedback-design doc in this project to build from — this
was the first pass.

## Decision

1. **Proceed with Claude Code's proposed plan**: a verdict/error_type/traceback → scaffolded-hint
   template layer on top of `classify.py`, evaluated first with a fast simulated-student loop
   (feed the hint to an LLM playing a novice who only sees the hint, measure fix-success rate /
   iterations-to-pass across the 25-case corpus) before spending real classroom-pilot effort. This
   matches the project's existing pattern of validating cheaply first (subprocess stand-in →
   real Judge0) before investing in expensive real infrastructure.

2. **Merge the feedback-template work with the hint-taxonomy backlog item instead of treating them
   as separate tasks.** "Scaffolded hint, not the fix" and "safe vs. answer-giving nudge" are the
   same underlying design question. The taxonomy (what counts as a legitimate hint vs. one that
   crosses the line) should be drafted as part of the template layer, not deferred as a separate
   follow-up.

3. **Add a middle rigor checkpoint between the simulated-student loop and any real classroom
   pilot.** The simulated-student proxy has a known blind spot: an LLM "student" doesn't fail the
   way a real beginner does, so it can overstate how helpful a hint is. Rather than jumping from
   the simulated loop straight to an IRB classroom pilot, insert a small human/expert spot-check
   pass (~20–30 generated hints, reviewed by supervisor or self) rating whether each one is
   actually a hint vs. a fix, and whether it's pedagogically sound. This mirrors ClassAid's own
   methodology (expert evaluation of feedback correctness on a sample of real interactions) and
   gives a defensible middle step before spending IRB overhead — also strengthens the "improve on
   ClassAid's evaluation rigor" angle already in the positioning doc.

## Resulting shape of the work

1. Draft hint taxonomy (safe scaffolds vs. answer-giving) as part of the template design, not
   after it.
2. Build the verdict → feedback-message template layer on `classify.py`.
3. Fast iteration: simulated-student eval loop across the 25-case corpus (extended to more
   exercises as needed).
4. Checkpoint: small human/expert review pass on a sample of generated hints before going further.
5. Only then: real classroom pilot (IRB, scheduling) to validate that the simulated results
   transfer to actual students.

## Hint escalation tiers (follow-up, 2026-09-15)

Once Claude Code started drafting the taxonomy, three concrete design questions came back:

1. Should tier be a single fixed default, or should it progress (1 → 2 → 3), matching how ITS
   hint sequences are normally consumed?
2. Do `function_not_found` and the syntax-error family need fewer than 4 meaningful tiers, since
   they compress toward the top of the scale faster than other verdicts?
3. Should the simulated-student eval score fix-success per tier?

**Answers:**

1. **Escalation, driven by `attempt_number`, not an explicit hint request.** The submission schema
   already tracks `attempt_number` per student+question for resubmission tracking
   (`submission-format-and-error-taxonomy.md` §1) — tier can be a function of that (attempt 1 →
   tier 1, attempt 2 → tier 2, ...) instead of adding new request/response UI, which fits the
   few-minutes lecture cycle much better. This is a separate layer from instructor-configurability
   (the open question below): per-student default escalation by attempt count, with an optional
   instructor-level override on top (force everyone to a fixed tier, ClassAid-mode-style) left as
   room to add later, not built now.

2. **Tier definitions stay uniform; the ceiling per verdict does not.** Keep a consistent 4-tier
   *definition* (tier 1 = flag a problem exists, tier 2 = point at location, tier 3 = name the
   mechanism/category, tier 4 = near-solution), but let each verdict cap escalation at whatever
   tier is actually meaningful for it. Syntax-error-family and `function_not_found` likely cap
   around tier 2 — there isn't much real space between "there's a problem" and "here's basically
   the fix" for those. Escalate by attempt_number up to the verdict's ceiling and hold there rather
   than padding out a redundant top tier.

3. **Yes — score fix-success per (verdict, tier), not just per case.** This is the empirical
   evidence for both #1 and #2: where the fix-success curve flattens per verdict tells you the
   real tier ceiling for that verdict and roughly what a sane default escalation rate looks like.
   Treat this as *relative* signal (where's the elbow, which tiers are redundant) rather than an
   absolute number to set defaults from directly — the simulated-student blind spot noted above
   still applies, which is exactly what the human/expert checkpoint (decision 3) exists to catch.

## Runtime resource finding (2026-09-15): local-laptop latency/memory ceiling

*Written by Claude Code after wiring the taxonomy into the running `interactive_lecture_prototype`
backend (`feedback-research/` copied in, `backend/ai_feedback.py` switched from Claude to a local
Ollama call for verdict/error_type/discussion_point) and testing it against 6 real submissions on
Lara's laptop. Logged here rather than left as a README footnote because it's directly relevant to
the open IDUN/VM access question, not just an implementation detail.*

**What was measured**: 6 real submissions through `/api/submit` (correct code, a wrong-answer bug,
and a `NameError` resubmitted 4 times to watch the hint escalate), with Judge0 (Docker), the FastAPI
backend, and Ollama (`llama3.2:3b`, chosen over the already-pulled `llama3.2:1b` — the 1b model was
deliberately picked *weak* for the simulated-student eval role above, the wrong property for a
grading role) all running together on one machine: 7.6GB RAM, no GPU.

**Findings**:
- Latency: first grading call after backend startup took ~38s (cold model load into RAM);
  subsequent calls to the same already-loaded model ranged ~9-33s. Noticeably slower than the
  Claude forced-tool-use call it replaced.
- Memory: swap was already at ~7.2-7.5GB/8GB used before this stack was even started (other running
  applications, not this stack alone). Available RAM dropped from ~2.0GB to ~1.2-1.3GB once the 3B
  model loaded, and stayed there — thin enough margin that heavier concurrent load (several students
  submitting at once, which this single-student sequential test does not exercise) could plausibly
  push it into real thrashing rather than just slow responses.

**Why this matters for the IDUN/VM access question**: this is real evidence, not a guess, that a
live classroom pilot run against local-laptop Ollama is risky on both axes that matter for a
lecture-paced feedback loop — tens-of-seconds latency per submission, and a memory margin thin
enough that it wasn't tested here under realistic multi-student concurrency. Whatever gets decided
on IDUN/VM access should treat this as the concrete cost of *not* moving the Ollama-serving
component off the local machine, weighed against however much simpler local-only stays for
day-to-day development. A fallback worth naming explicitly if IDUN access doesn't land in time:
keep local Ollama for day-to-day dev/testing (as now) but reconsider whether the actual classroom
pilot needs a hosted model (Claude, or Ollama on a properly resourced VM) for the grading role,
purely on latency/reliability grounds — independent of the hint-taxonomy work, which doesn't depend
on Ollama at all and is unaffected either way.

## Open questions this still leaves

- Who reviews the expert-checkpoint sample — supervisor, self, or both?
- How big does the corpus need to grow before the simulated-student signal is trustworthy across
  more than one exercise (`is_palindrome`)?
- Instructor-level tier override (force a fixed tier class-wide, ClassAid-mode-style): worth
  designing now or deferred until the per-attempt default is validated?
- Once per-(verdict, tier) fix-success data exists, what threshold on the curve actually decides
  "this verdict's ceiling is N tiers" — a fixed drop-off percentage, or a judgment call reviewed
  at the human-checkpoint stage?
- IDUN/VM access: does the classroom-pilot deployment move the Ollama-serving component off the
  local laptop, and if so, on what timeline relative to the pilot itself? The 2026-09-15 local-run
  numbers above (latency, memory margin) are the concrete cost of leaving it local-only.
