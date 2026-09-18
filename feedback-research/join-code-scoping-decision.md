# Join-code scoping decision (2026-09-18)

*Captures a new student-page entry step: a Kahoot-style "enter the code"
screen before the name/code editor, requested as a lightweight way for
students to deliberately "enter" a lecture rather than just landing on a
plain URL.*

## Context

The student page has always had no entry step at all -- `student.html` (or
`?question_id=...`) goes straight to the name/code editor for whatever
question is live (see the README's "No auth" known simplification). That's
fine for a controlled lecture-hall setting, but it means there's no moment
that says "you're now in this specific lecture," the way a Kahoot game PIN
does for students joining a live quiz.

## Decision

1. **A 6-digit numeric join code**, minted once per lecture (`create_lecture`
   in `backend/store.py`, `lectures.join_code`) -- the same shape as a
   Kahoot PIN: easy to read aloud or project, easy to type on a phone.
2. **Shown to the lecturer** on the home dashboard's "Lecture in progress"
   card and on the live task-control dashboard (`lecturer/App.tsx`) for the
   whole session, the way a Kahoot host screen keeps the PIN visible.
3. **A new student-page phase** (`join`, `student/App.tsx`) gates the
   existing name/code editor behind a code-entry screen. `POST
   /api/lecture/join` validates it against the active lecture
   (case/whitespace-insensitive) and, once accepted, the tab remembers it
   (`sessionStorage`) so a refresh mid-lecture doesn't force retyping it.

## Deliberately not real access control

This is a UX gate, not auth: `/api/submit` and every other endpoint stay
exactly as open as before (see README's "No auth" simplification, which this
doesn't change). A wrong or missing code only affects whether the student
page's join screen lets a browser tab past itself -- it doesn't gate
anything at the API level, there's no rate limiting on guesses, and the code
is a plain 6-digit number with no uniqueness check against other lectures
(unnecessary: this backend only ever runs one lecture at a time, see
`create_lecture`'s docstring). Treating it as more than that would be
over-building for a lecture-hall MVP where the actual security boundary
(Judge0 sandboxing untrusted code execution) is elsewhere entirely.

## Known limitation

A fresh checkout's pre-seeded `sum-ints` lecture needed a join code too
(`init_db`'s seeding path in `backend/store.py`), and an existing DB
migrating in from before this feature needed the *currently active* lecture
backfilled with one -- otherwise the student page's join screen would have
had nothing valid to accept until a lecturer happened to click "New
lecture." Historical (already-ended) lectures are left with `join_code =
NULL`; nobody needs to join one that's over, and old rows have no reliable
code to backfill anyway.
