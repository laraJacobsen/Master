# Interactive Lecture Prototype -- Vertical Slice

A thin end-to-end slice of the system from the thesis proposal: a student
submits code, it's graded on Judge0 (the same execution engine from the
scaling spike), a local Ollama model produces a verdict + lecturer discussion
point, a deterministic tiered-hint taxonomy produces the student-facing
feedback text (escalating across resubmissions), and the lecturer sees
submissions and discussion points appear live.

One question ships pre-seeded (already `live`): "read space-separated
integers from stdin, print their sum" (Python). Beyond that, a lecturer
authors questions through the setup/landing page (`frontend/setup.html`)
rather than editing `backend/questions.py` directly -- see
`feedback-research/landing-page-scoping-decision.md` for the scoping
decision behind that flow (prompt/rubric/language, per-question Judge0
resource limits, a validation preview against a reference solution before
a question can go live, and the "start" action that flips it live).

## What's included

```
backend/
  judge0_client.py   Judge0 SYNC submission wrapper (reuses the pattern from
                      the earlier latency/scaling benchmark scripts); per-question
                      cpu_time_limit/memory_limit are passed through here and capped
                      server-side (MAX_CPU_TIME_LIMIT/MAX_MEMORY_LIMIT_KB env vars)
  validation.py        Pre-execution checks (empty/whitespace/too-long/encoding/
                        disallowed-package) run before code ever reaches Judge0 --
                        line limit and package allow-list are per-question knobs
  questions.py        Question lookup, backed by store.py's `questions` table
  ai_feedback.py       Local Ollama call -> verdict + discussion point; also calls
                        hints.py for exec_verdict + the student-facing hint text
  hints.py             THE deterministic Judge0-result classifier (via
                        feedback-research/classify.py) plus tier-escalating hint
                        lookup (via feedback-research/feedback.py) -- one
                        classification of a submission feeds both the
                        exec_verdict column (lecturer aggregation) and the hint
                        text (student feedback). There used to be a second,
                        coarser classifier here (exec_verdict.py) duplicating
                        this job with less detail -- retired in favor of this
                        one, single source of truth.
  store.py             SQLite store (backend/prototype.db, created on first run):
                        submissions, and the `questions` table (draft -> validated
                        -> live), with the MVP question seeded live on first run
  main.py               FastAPI app: /api/submit, /api/questions (live questions
                        only), /api/lecturer/submissions, /api/lecturer/clusters,
                        /api/lecturer/questions* (setup: create/list/detail/update/
                        validate/start)
feedback-research/    Tiered-feedback taxonomy + eval corpus, imported from the
                        classification-test work (see its own docs in this folder)
frontend/              React + TypeScript (Vite), one entry point per page -- same
                        URLs/behavior as before, just a different tech stack. Built
                        to frontend/dist/, which backend/main.py serves as static
                        files. See frontend/README.md.
  src/setup/            Lecturer question-setup/landing page: author a question,
                        set its grading config, run the validation preview, start it
  src/student/          Student page: name, code box, submit, see feedback + hint tier
  src/lecturer/         Lecturer page: live table of submissions + discussion points
                        (polls every 3s) for one question, picked via ?question_id=
  src/shared/           TypeScript types + fetch wrappers for the API, shared by
                        all three pages
smoke_test.py           Structural test with Judge0 + Ollama mocked out -- proves the
                          plumbing works without needing either service running, including
                          the full question-setup flow (draft -> validate -> start -> live,
                          plus per-question line_limit/package-allowlist enforcement).
                          Already run; see "What's been verified" below.
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
4. Node 18+ (to build the frontend).

## Running it

```bash
cd prototype
pip install -r requirements.txt

cd frontend && npm install && npm run build && cd ..   # builds frontend/dist

ollama pull llama3.2:3b                         # once, if not already pulled
export OLLAMA_MODEL=llama3.2:3b                  # only if you want a different model
export JUDGE0_BASE_URL=http://localhost:2358     # only if not the default

uvicorn backend.main:app --reload --port 8000
```

(For frontend development with hot reload instead of a static build, run
`npm run dev` in `frontend/` alongside the backend -- see `frontend/README.md`.)

Then open in a browser:

- Question setup (lecturer): `http://localhost:8000/setup.html` -- author a
  question, set its grading config, run the validation preview against a
  reference solution, then start it. The pre-seeded `sum-ints` question is
  already live, so this step is only needed to add more questions.
- Student page: `http://localhost:8000/student.html?question_id=sum-ints`
  (or whatever question id you started; with no `question_id`, it falls back
  to the first live question)
- Lecturer page: `http://localhost:8000/lecturer.html?question_id=sum-ints`
  (the setup page's "Start"/"Live dashboard" links go here directly; with no
  `question_id` it shows submissions across every question, the old behavior)

Open the student and lecturer pages side by side (or on two machines on the
same network, using your laptop's IP instead of `localhost`) to see a
submission on the student page show up on the lecturer page a few seconds
later.

Submissions and questions are stored in `backend/prototype.db` (SQLite) --
delete that file to start a clean session (this also clears any questions
authored through the setup page, back down to just the pre-seeded one).

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

- Question authoring now goes through `frontend/setup.html`, but the student
  page has no question *picker* -- it takes `?question_id=` (or falls back to
  the first live question), so more than one live question at a time isn't
  really usable from the student side yet.
- Package allow-list enforcement (`backend/validation.py`) is a static check
  of `import`/`from` statements against stdlib + the question's configured
  extras -- it doesn't stop a workaround like `__import__("os")`, and isn't
  meant to (this is a lecture-hall classroom tool, not a hostile sandbox
  boundary; Judge0 itself is the actual execution sandbox).
- No auth -- anyone who can reach the URL can submit as any name, and anyone
  who can reach `/setup.html` can author/start questions.
- Lecturer page polls every 3 seconds rather than pushing updates (no
  websockets yet) -- fine for a lecture-sized class, revisit if this needs
  to feel more instant.
- Two verdict fields per submission, deliberately not merged: `verdict`/
  `error_type` are the local model's own judgment (feeds lecturer discussion
  points), while `exec_verdict`/`rejection_reason` are a deterministic
  classification of the raw Judge0 result (lecture-wide aggregation, e.g.
  "how many students hit a timeout") -- computed by `backend/hints.py`, the
  same classifier that drives the hint tier shown to the student, so there's
  one deterministic classification per submission, not two. (There used to
  be a second, coarser deterministic classifier -- `backend/exec_verdict.py`
  -- duplicating this job with less detail; retired once the hint-taxonomy
  classifier could do both jobs.) A rejected submission (empty/whitespace/
  too-long/bad encoding) still gets a 200 response and a stored row -- it's
  tagged `exec_verdict="rejected"` rather than bounced with an HTTP error, so
  it shows up in the same aggregation as everything else.
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
