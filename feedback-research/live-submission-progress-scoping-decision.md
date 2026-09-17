# Live submission progress scoping decision (2026-09-17)

*Captures a dashboard feature not currently in `frontend/lecturer.html`: a live
count of how many of N students have submitted vs. not, updating in real time.
Motivated by two problems already flagged elsewhere (low/missing submission
rates going unnoticed during a live session, and the lecturer having no signal
for when to move on) and the same real-time-visibility goal VizProg and
ClassAid were both built around.*

## Context

`lecturer.html` currently shows submissions as they arrive (a live-polled
table) and clustered issues/discussion points, but nothing about the class as
a whole -- there's no sense of "how many students are still working" versus
"how many have already submitted." A lecturer watching the table has no way
to tell, at a glance, whether 3 students haven't submitted yet or 15 have,
which is exactly the signal needed to decide whether to keep waiting or move
on, and to notice a participation problem in time to do something about it.

## Decision

1. **Live "X/N submitted" counter** on the lecturer dashboard, updating on the
   same poll cycle as the rest of the page (currently every 3s). Even a bare
   count earns its place -- this doesn't need to be a chart or a list to be
   useful.
2. **A visible not-yet-submitted count** (a number, not names) as a stopgap
   -- enough for the lecturer to know to prompt the class verbally, without
   yet needing the idle-student-nudge feature (a separate, not-yet-designed
   piece of work).

## Where N comes from (resolved 2026-09-17)

This feature's only real complexity is the denominator: nothing in the
system tracks a class roster or expected headcount, since submissions are
just a student-supplied free-text name with no registration step. **Decision:
the lecturer types a plain class-size number** (`expected_students`) as part
of a question's config, on the setup page -- the cheapest option of the ones
considered (versus an actual roster upload, or a live "join" step producing a
headcount some other way). It's optional: a question with no number set just
shows a submitted count with no denominator, rather than blocking the
feature on every question having one.

Known limitation this decision accepts: the count is only as accurate as
what the lecturer typed in, and doesn't track *who* hasn't submitted (no
roster of names exists) -- true attendance can drift from it, and there's no
name-level "not yet submitted" list, just a number. If a future roster-based
feature (e.g. the idle-student nudge) needs actual names, that's a separate,
larger piece of work building on a real roster, not an extension of this
plain-number field.
