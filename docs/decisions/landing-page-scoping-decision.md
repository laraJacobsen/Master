# Landing page (question setup) scoping decision (2026-09-17)

*Captures the answer to "what should the landing page include?" -- the pre-live,
question-setup view a lecturer uses before a question goes live, as distinct from
the live lecturer-dashboard view (submission progress, verdict breakdown,
discussion points) that takes over once a question starts. Cross-referenced
against `run-judge0-locally.md`'s config-knob table and the
[Sep 15 pedagogical-feedback decision](pedagogical-feedback-design-decision.md).*

## Context

The lecturer dashboard work so far (`frontend/lecturer.html`, `backend/main.py`'s
`/api/lecturer/submissions`) assumes a question is already live and submissions
are flowing in. There's currently no UI for the step before that: authoring a
question and its grading config, and no notion of "live" vs. "not yet started" at
all -- the one MVP question in `backend/questions.py` is just always live. This
decision scopes the landing page that fills that gap.

## Decision

**Question setup** -- the prompt text, the test cases/rubric the submission is
graded against, and the language. This maps onto the existing `questions.py`
schema (`prompt`, `test_cases`, `language`), moved from a hardcoded dict into
something a lecturer fills in through the landing page.

**Per-question config knobs**, exposed as real teacher-facing controls (not
placeholders):

- Time limit per submission (`CPU_TIME_LIMIT`, defaults to 5s, capped at
  `MAX_CPU_TIME_LIMIT`)
- Memory limit (`MEMORY_LIMIT`, defaults ~125MB, capped at `MAX_MEMORY_LIMIT`)
- Package allow-list -- default stdlib-only, teacher can widen. This one's
  already a firm decision, so it belongs here as a real control, not a
  placeholder.
- Submission line-limit (100-200 lines)

None of these exist in `backend/judge0_client.py` yet -- it currently sends only
`language_id`/`source_code`/`stdin` with no resource limits set, so wiring these
through is new work, not a config surface on top of something already there.

**Validation/preview step** before opening the question up: run the rubric
against at least one known-correct solution before going live, so a broken test
case doesn't surface live in front of the class. Nothing in the existing docs
describes this explicitly, but it's cheap insurance given how much of the
existing work (the 25-case corpus, the Judge0 verification in the Sep 15 doc's
runtime-resource findings) has been about getting the grading right before
trusting it live.

**A "start" action** that flips the question from setup into the live state --
the boundary where the live lecturer-dashboard view (submission progress,
verdict breakdown, discussion points) takes over.

## Open questions this leaves

- Where do the `MAX_CPU_TIME_LIMIT`/`MAX_MEMORY_LIMIT` ceilings themselves get
  set -- hardcoded in the backend, an env var alongside `JUDGE0_BASE_URL`, or a
  separate admin-level config above the per-question teacher knobs?
- What counts as the "known-correct solution" for the preview step -- does the
  lecturer supply one per question at setup time, or is this expected to reuse
  a solution already sitting in the 25-case corpus?
- Package allow-list widening: freeform (teacher types any package name) or a
  curated list they pick from?
- Does starting a question lock its config (test cases, limits) against
  further edits, or can a lecturer still tweak it once live and submissions
  exist against the old config?
- `questions.py` is currently a hardcoded dict with one entry and no
  persistence -- does question setup write into SQLite (alongside
  `prototype.db`'s submissions table) or somewhere else?
