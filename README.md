# Interactive Lecture Prototype -- Vertical Slice

A thin end-to-end slice of the system from the thesis proposal: a student
submits code, it's graded on Judge0 (the same execution engine from the
scaling spike), Claude produces a verdict + student feedback + a lecturer
discussion point in one call, and the lecturer sees submissions and
discussion points appear live.

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
  ai_feedback.py       One combined Claude call -> verdict + feedback + discussion point
  store.py             SQLite session store (backend/prototype.db, created on first run)
  main.py               FastAPI app: /api/submit, /api/questions, /api/lecturer/submissions
frontend/
  student.html          Student page: name, code box, submit, see feedback
  lecturer.html         Lecturer page: live table of submissions + discussion points (polls every 3s)
smoke_test.py           Structural test with Judge0 + Claude mocked out -- proves the
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
2. **An Anthropic API key.** Set `ANTHROPIC_API_KEY` in your environment.
3. Python 3.9+.

## Running it

```bash
cd prototype
pip install -r requirements.txt

export ANTHROPIC_API_KEY=sk-ant-...
export JUDGE0_BASE_URL=http://localhost:2358   # only if not the default

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

`smoke_test.py` runs the full FastAPI app with Judge0's HTTP API and the
Anthropic API both mocked out (no live Judge0, no API key needed), and
checks: the questions endpoint, a full submit -> grade -> feedback -> store
round trip, the lecturer submissions list, a submission detail lookup, a
404 on an unknown question, and that both frontend pages are served. All
of that passes as of this build.

**Not yet verified** -- needs a real run to confirm: actual Judge0
execution under this new client code (as opposed to the standalone
benchmark scripts), real Claude output quality/latency for the feedback
call, and the lecturer page's live-polling feel with more than one student
submitting at once. Try it against your real Judge0 instance next.

## Known simplifications (MVP, not final)

- One question, Python only. No question-authoring UI -- edit
  `backend/questions.py` directly to add more.
- No auth -- anyone who can reach the URL can submit as any name.
- Lecturer page polls every 3 seconds rather than pushing updates (no
  websockets yet) -- fine for a lecture-sized class, revisit if this needs
  to feel more instant.
- Two verdict fields per submission, deliberately not merged: `verdict`/
  `error_type` are Claude's own judgment (student-facing feedback), while
  `exec_verdict`/`rejection_reason` are a deterministic classification of
  the raw Judge0 result (lecture-wide aggregation, e.g. "how many students
  hit a timeout"). A rejected submission (empty/whitespace/too-long/bad
  encoding) still gets a 200 response and a stored row -- it's tagged
  `exec_verdict="rejected"` rather than bounced with an HTTP error, so it
  shows up in the same aggregation as everything else.
- `attempt_number` increments per (student_name, question_id) pair by
  counting existing rows -- fine for a single student's sequential
  submissions, not race-safe against truly concurrent double-submits from
  the same student.
- Single combined Claude call per submission (grading interpretation +
  feedback + discussion point) rather than separate calls -- cheaper and
  simpler, but means you can't easily swap out just the "discussion point"
  logic without touching the same call.
- No rate limiting -- if many students submit in the same second, you'll
  send that many concurrent Judge0 + Claude calls. Worth watching if this
  becomes a real concern, informed by what you already know about Judge0's
  worker-count ceiling from the scaling spike.
# Master
