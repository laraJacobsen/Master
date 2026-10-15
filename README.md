# Interactive Lecture Prototype -- Vertical Slice

A thin end-to-end slice of the system from the thesis proposal: a student
submits code, it's graded on Judge0 (the same execution engine from the
scaling spike), a deterministic tiered-hint taxonomy produces the verdict and
the student-facing feedback text (escalating across resubmissions), and the
lecturer sees submissions appear live, grouped into common issues with a
discussion point per issue. Grading has no model in the loop; the only LLM
call is IDUN (NTNU's hosted gateway) writing discussion points for groups of
wrong-answer submissions on the lecturer side.

One question ships pre-seeded (already `live`): "read space-separated
integers from stdin, print their sum" (Python). Beyond that, a lecturer
authors questions through the setup/landing page (`frontend/setup.html`)
rather than editing `backend/questions.py` directly -- see
`docs/decisions/landing-page-scoping-decision.md` for the scoping
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
  ai_feedback.py       Grading, fully deterministic (no model): verdict from the
                        test pass/fail counts, exec_verdict/error_type + the
                        student-facing hint text from hints.py. (Name is historical
                        -- this used to be a local Ollama call; see its docstring.)
  aggregation.py       Groups a question's submissions into common issues by
                        (exec_verdict, error_type), counted per distinct student,
                        with one discussion point per issue: a curated line for
                        most categories, an IDUN LLM call for wrong_answer
                        sub-clusters (code-similarity grouping). Also holds the
                        lecturer's "Show to students" flags (in-memory only)
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
                        classification-test work
  classify.py,          Loaded by backend/hints.py at runtime -- the only files here
  feedback.py           the app needs (with hint-taxonomy-draft.md, their design doc)
  corpora/              Hand-written bug corpora per exercise (is_palindrome, ...)
  clustering-eval/      wrong_answer sub-clustering ground truth + scoring scripts
                        (run_*_baseline.py, subcluster_eval.py)
  label-spot-checks/    Discussion-point Label rounds 1-5 (generated samples + ratings,
                        latency) and the generator script
  decisions/            Feedback/clustering design decisions and known limitations
docs/decisions/        App feature scoping decisions (join code, landing page, live
                        progress, class-progress visualization)
frontend/              React + TypeScript (Vite), one entry point per page -- same
                        URLs/behavior as before, just a different tech stack. Built
                        to frontend/dist/, which backend/main.py serves as static
                        files. See frontend/README.md.
  src/setup/            Lecturer question-setup/landing page: author a question,
                        set its grading config, run the validation preview, start it
  src/student/          Student page: join code, then whatever the lecturer has live --
                        code box + submit + feedback/hint tier while a task runs, a
                        waiting screen between tasks (see "Running it" below).
                        The code box is Monaco (the VS Code editor, CodeEditor.tsx), which also
                        drives the activity heartbeat + idle nudge (see
                        docs/decisions/class-progress-visualization-decision.md)
  src/lecturer/         Lecturer page: live table of submissions + discussion points
                        (polls every 3s) for one question, picked via ?question_id=,
                        plus a class-progress chart (ClassProgress.tsx; see
                        docs/decisions/class-progress-visualization-decision.md)
  src/history/          Lecture history (nav bar "History"): "Needs revisiting" ranks
                        finished lectures by share of students who solved each task,
                        worst first, with each one's weakest tasks and most common issue
                        (GET /api/lecturer/lectures/review); plus the full lecture list
  src/shared/           TypeScript types + fetch wrappers for the API, shared by
                        all pages
smoke_test.py           Structural test with Judge0 + IDUN mocked out -- proves the
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
2. **An IDUN API key** (optional) for the wrong-answer discussion points.
   Put `IDUN_API_KEY=...` in `.idun.env` at the repo root (gitignored) and
   load it before starting the backend (see below). IDUN needs the NTNU
   network or VPN. Overrides: `IDUN_BASE_URL` (default
   `https://llm.hpc.ntnu.no/v1`) and `IDUN_MODEL` (default
   `openai/gpt-oss-120b`). Without a key, everything still works; wrong-answer
   issues just get a generic discussion point instead of a generated one.
   Grading and student hints never depend on IDUN.
3. Python 3.9+.
4. Node 18+ (to build the frontend).

## Running it

```bash
# from the repo root
pip install -r requirements.txt

cd frontend && npm install && npm run build && cd ..   # builds frontend/dist

set -a; . ./.idun.env; set +a                    # loads IDUN_API_KEY (skip if you have no key)
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
- Student page: `http://localhost:8000/student.html`. First shows a
  Kahoot-style "enter the code" screen -- the join code for the currently
  live lecture is shown on the home page (and on the live task-control
  dashboard) once a lecture is active; a fresh checkout's pre-seeded lecture
  already has one. Entering it is remembered for the rest of that browser
  tab, but only for that lecture: once the lecture ends, a refresh goes back
  to the code screen, and if the lecturer starts a new lecture an open tab
  is sent back there by itself ("A new lecture has started"). From there the page follows the lecture on its own (it polls
  `/api/lecture/status` every 2s): no `question_id` needed, it always shows
  the task the lecturer has live.

  Whenever there's nothing to type, the student sees one centered waiting
  screen whose text depends on what they just did:
  - joined, no task started yet -- "You're in! Waiting for your lecturer to
    start the first task."
  - correct submission -- "Good job!", straight away, even with time left
  - time's up after a wrong answer -- "Thanks for submitting", with their
    verdict (the hint stays on the task page)
  - time's up with nothing submitted -- "Time's up, no code submitted"
  - time's up mid-grading -- a spinner until the auto-submitted code is graded

  A wrong answer does *not* go to the waiting screen while time remains: the
  student stays on the editor with their hint and can resubmit, since
  resubmitting is what escalates the hint tier. Issues the lecturer flags
  with "Show to students" (anonymous code + failing test) appear on this
  waiting screen once the task's time is up.
- Lecturer page: `http://localhost:8000/lecturer.html?question_id=sum-ints`
  (the setup page's "Start"/"Live dashboard" links go here directly; with no
  `question_id` it shows submissions across every question, the old behavior).
  The "Task control" card at the top runs the lecture:
  - **End task now** (while the timer runs) -- ends the task early, e.g.
    everyone has answered. It doesn't move on: the task goes straight to
    "Time's up", exactly as if the timer had run out (students' unsubmitted
    code is auto-submitted and they land on the waiting screen), so you can
    go over the results and use "Show to students" first. Under the hood it
    shortens the task's stored `duration_seconds` to the time already used.
  - **Next task** -- closes the current task and starts the next unstarted
    one, in creation order.
  - **End lecture...** -- a small link at the bottom of the card, kept out of
    the main button row on purpose, behind an "are you sure" popup (with
    "Keep going" as the default button). Ends the lecture for everyone.
    Tasks that were never started are retired as `skipped` under that
    lecture: they aren't carried into the next lecture, and they don't count
    as tasks in its summary or history. (Tasks authored while no lecture is
    running still wait for the next one. A one-time startup migration also
    retires leftovers from lectures that ended before this existed.)

Open the student and lecturer pages side by side (or on two machines on the
same network, using your laptop's IP instead of `localhost`) to see a
submission on the student page show up on the lecturer page a few seconds
later.

Submissions and questions are stored in `backend/prototype.db` (SQLite) --
delete that file to start a clean session (this also clears any questions
authored through the setup page, back down to just the pre-seeded one).

## What's been verified

`smoke_test.py` runs the full FastAPI app with Judge0's HTTP API and
IDUN's chat-completions API both mocked out (no live Judge0, no IDUN key or
VPN needed), and checks: the questions endpoint, a full submit -> grade ->
feedback -> store round trip, the lecturer submissions list, a submission
detail lookup, a 404 on an unknown question, the question-setup and lecture
flows, issue clustering (including that the IDUN call never sees student
names or comments), and that the frontend pages are served. All of that
passes as of this build.

The student page's join -> task -> waiting-screen flow (correct answer,
wrong answer + retry, time's up with and without a submission, and a
"Show to students" example) has been driven end to end in a real browser
against live Judge0.

Earlier versions graded with a local Ollama model (`llama3.2:3b`). That was
removed: it was unreliable at explaining causes, and slow (~9-38s per call)
and memory-hungry on this 7.6GB, no-GPU laptop. See
`feedback-research/decisions/pedagogical-feedback-design-decision.md` for the history.

**Not yet verified**: the lecturer page's live-polling feel with more than
one student submitting at once, and behavior under concurrent submissions
(Judge0 serializes/queues under load in ways a single-student manual test
doesn't exercise). The IDUN-generated wrong-answer discussion points haven't
been through the human spot-check pass yet (see `backend/aggregation.py`'s
module docstring).

## Known simplifications (MVP, not final)

- Question authoring now goes through `frontend/setup.html`, but the student
  page has no question *picker* -- it always shows the single task the
  lecturer has live, so more than one live question at a time isn't
  supported from the student side.
- The live "X/N submitted" counter's denominator is just a number the
  lecturer typed in at setup time (see
  `docs/decisions/live-submission-progress-scoping-decision.md`), so more
  students can submit than were expected -- the lecturer dashboard shows
  that as "N submitted (more than the M expected)" rather than a raw
  numerator-over-denominator that reads like an error.
- Package allow-list enforcement (`backend/validation.py`) is a static check
  of `import`/`from` statements against stdlib + the question's configured
  extras -- it doesn't stop a workaround like `__import__("os")`, and isn't
  meant to (this is a lecture-hall classroom tool, not a hostile sandbox
  boundary; Judge0 itself is the actual execution sandbox).
- No auth -- anyone who can reach the URL can submit as any name, and anyone
  who can reach `/setup.html` can author/start questions. The student page's
  join code (see "Running it" above) is a Kahoot-style soft gate for casual
  access, not real access control: `/api/submit` and every other endpoint
  stay open regardless, and the code itself is a plain 6-digit number with
  no rate limiting on guesses.
- Lecturer page polls every 3 seconds rather than pushing updates (no
  websockets yet) -- fine for a lecture-sized class, revisit if this needs
  to feel more instant.
- Two verdict fields per submission: `verdict` is a coarse bucket for the
  student-facing badge (correct/partially_correct/incorrect/error, a plain
  threshold on tests passed), while `exec_verdict`/`error_type`/
  `rejection_reason` are the detailed classification of the raw Judge0
  result (lecture-wide aggregation, e.g. "how many students hit a
  timeout") -- computed by `backend/hints.py`, the same classifier that
  drives the hint tier shown to the student, so there's one deterministic
  classification per submission, not two. (There used to
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
- Discussion points (and "Show to students" flags) are cached in memory,
  so restarting the backend regenerates them and forgets the flags.
- No rate limiting -- if many students submit in the same second, you'll
  send that many concurrent Judge0 calls. Worth watching if this becomes a
  real concern, informed by what you already know about Judge0's
  worker-count ceiling from the scaling spike. IDUN calls are capped at 8
  in parallel and only happen when the lecturer dashboard asks for issues,
  not per submission.
# Master
