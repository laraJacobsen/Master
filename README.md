# Interactive Lecture Prototype -- Vertical Slice

A thin end-to-end slice of the system from the thesis proposal: a student
submits code, it's graded on Judge0 (the same execution engine from the
scaling spike), a local Ollama model produces a verdict + lecturer discussion
point, a deterministic tiered-hint taxonomy produces the student-facing
feedback text (escalating across resubmissions), and the lecturer sees
submissions and discussion points appear live.

One question is wired up for now: "read space-separated integers from
stdin, print their sum" (Python). The point of this slice is to prove the
pipeline works end to end, not to have a full question bank yet -- add more
entries to `backend/questions.py` once this is confirmed working.

## What's included

```
backend/
  judge0_client.py   Judge0 SYNC submission wrapper (reuses the pattern from
                      the earlier latency/scaling benchmark scripts)
  validation.py        Pre-execution checks (empty/whitespace/too-long/encoding) run
                        before code ever reaches Judge0
  exec_verdict.py       Deterministic verdict taxonomy (pass/wrong_answer/syntax_error/
                        runtime_error/timeout/oom/function_not_found/rejected) from raw
                        Judge0 results -- separate from Claude's own verdict below
  questions.py        The question bank (one MVP question)
  ai_feedback.py       Local Ollama call -> verdict + discussion point; student-facing
                        feedback text comes from hints.py instead (see below)
  hints.py             Bridges feedback-research/'s classify.py + feedback.py into the
                        backend -- turns a failing test case into a tier-escalating hint
  store.py             SQLite session store (backend/prototype.db, created on first run)
  main.py               FastAPI app: /api/submit, /api/questions, /api/lecturer/submissions
feedback-research/    Tiered-feedback taxonomy + eval corpus, imported from the
                        classification-test work (see its own docs in this folder)
frontend/
  student.html          Student page: name, code box, submit, see feedback + hint tier
  lecturer.html         Lecturer page: live table of submissions + discussion points (polls every 3s)
smoke_test.py           Structural test with Judge0 + Ollama mocked out -- proves the
                          plumbing works without needing either service running. Already run;
                          see "What's been verified" below.
requirements.txt
```

## Prerequisites

1. **A running Judge0 instance.** Use the same `docker-compose` setup from
   the scaling spike (`judge0-v1.13.1/`), with however many workers you
   found reasonable (4 was the sweet spot on the VM). Default expected URL
   is `http://localhost:2358` -- override with the `JUDGE0_BASE_URL`
   environment variable if yours is elsewhere.
2. **Ollama running locally**, with a model pulled. Default expected model
   is `llama3.2:3b` (`ollama pull llama3.2:3b`) -- override with
   `OLLAMA_MODEL`. Default URL is `http://localhost:11434` -- override with
   `OLLAMA_URL`. If Ollama isn't reachable or the model isn't pulled, the
   backend falls back to mock verdict/discussion-point text automatically
   (the tiered hint text still works either way -- it doesn't depend on
   Ollama at all).
3. Python 3.9+.

## Running it

```bash
cd prototype
pip install -r requirements.txt

ollama pull llama3.2:3b                         # once, if not already pulled
export OLLAMA_MODEL=llama3.2:3b                  # only if you want a different model
export JUDGE0_BASE_URL=http://localhost:2358     # only if not the default

uvicorn backend.main:app --reload --port 8000
```

Then open in a browser:

- Student page: `http://localhost:8000/student.html`
- Lecturer page: `http://localhost:8000/lecturer.html`

Open both side by side (or on two machines on the same network, using your
laptop's IP instead of `localhost`) to see a submission on the student page
show up on the lecturer page a few seconds later.

Submissions are stored in `backend/prototype.db` (SQLite) -- delete that
file to start a clean session.

## What's been verified

`smoke_test.py` runs the full FastAPI app with Judge0's HTTP API and
Ollama's HTTP API both mocked out (no live Judge0, no Ollama needed), and
checks: the questions endpoint, a full submit -> grade -> feedback -> store
round trip, the lecturer submissions list, a submission detail lookup, a
404 on an unknown question, and that both frontend pages are served. All
of that passes as of this build.

**Verified against a real, running Judge0 + Ollama (`llama3.2:3b`)**: 6
real submissions through `/api/submit` (correct code, a wrong-answer bug,
and a `NameError` resubmitted 4 times to watch the hint escalate). All 6
came back with schema-valid, sensible `verdict`/`error_type`/
`discussion_point` on the first try -- no retry or mock-fallback was
triggered in this run. `error_type` was correct in every case
(`"runtime"` for the `NameError`, `"logic"` for the wrong-answer bug), and
`hint_tier` climbed 1 -> 2 -> 3 with different, correctly-escalating hint
text each time, then held at tier 3/3 on the 4th resubmission rather than
reaching the unshipped bottom-out tier. Sample size is small (one model,
one session, no adversarial inputs) -- treat this as "worked, not flaky
today," not a reliability guarantee; the retry-then-mock-fallback path
exists precisely because a small local model won't always be this clean.

Latency: the first call after starting the backend took ~38s (cold model
load into RAM); subsequent calls to the same already-loaded model ranged
~9-33s. That's noticeably slower than Claude's forced-tool-use call was --
worth keeping in mind for how a live class period actually feels, not just
whether the output is correct.

Memory: this machine has only 7.6GB RAM and no GPU. With Judge0 (in
Docker), the backend, and Ollama all running together, available memory
dropped from ~2.0GB to ~1.2-1.3GB once the 3B model was loaded, and swap
was already sitting at ~7.2-7.5GB/8GB used throughout (largely from other
running applications, not this stack alone) -- close enough to the ceiling
that a heavier concurrent load (several students submitting at once, or
just more background apps open) could start swapping/thrashing. Not
observed to fail in this test, but the margin is thin enough to watch
before relying on this for an actual class.

**Not yet verified**: the lecturer page's live-polling feel with more than
one student submitting at once, and behavior under concurrent submissions
(Judge0 + Ollama both serialize/queue under load in ways a single-student
manual test doesn't exercise).

## Known simplifications (MVP, not final)

- One question, Python only. No question-authoring UI -- edit
  `backend/questions.py` directly to add more.
- No auth -- anyone who can reach the URL can submit as any name.
- Lecturer page polls every 3 seconds rather than pushing updates (no
  websockets yet) -- fine for a lecture-sized class, revisit if this needs
  to feel more instant.
- Two verdict fields per submission, deliberately not merged: `verdict`/
  `error_type` are the local model's own judgment (feeds lecturer
  discussion points), while `exec_verdict`/`rejection_reason` are a
  deterministic classification of the raw Judge0 result (lecture-wide
  aggregation, e.g. "how many students hit a timeout"). A rejected
  submission (empty/whitespace/too-long/bad encoding) still gets a 200
  response and a stored row -- it's tagged `exec_verdict="rejected"` rather
  than bounced with an HTTP error, so it shows up in the same aggregation
  as everything else. Yet a *third*, independent classification
  (`feedback-research/classify.py`, via `backend/hints.py`) drives the
  hint tier shown to the student -- it's the one evaluated against the
  hint taxonomy specifically, and deliberately not reconciled with the
  other two; see `backend/hints.py`'s docstring.
- `attempt_number` increments per (student_name, question_id) pair by
  counting existing rows -- fine for a single student's sequential
  submissions, not race-safe against truly concurrent double-submits from
  the same student.
- Local Ollama call per submission for verdict + discussion point only;
  student-facing feedback text no longer comes from the model at all --
  it's the deterministic, tier-escalating hint from `feedback-research/`.
  A JSON-mode call to a small local model doesn't have Claude's
  forced-tool-use guarantee, so it's validated defensively and retried
  once before falling back to mock text -- see `backend/ai_feedback.py`.
- No rate limiting -- if many students submit in the same second, you'll
  send that many concurrent Judge0 + Ollama calls. Worth watching if this
  becomes a real concern, informed by what you already know about Judge0's
  worker-count ceiling from the scaling spike -- and Ollama itself may
  serialize concurrent requests on constrained hardware.
# Master
