# Class progress visualization decision (2026-10-15)

*Supervisors asked for a visual way for the lecturer to follow student
progress during a task: who is getting there, who keeps hitting errors, who is
correct. Constraints given: not complicated, not visually disturbing, and
collapsible. This builds on the "X/N submitted" counter from
`live-submission-progress-scoping-decision.md` and replaces its plain progress
bar.*

## What the related work suggests

- **VizProg** (Zhang, Chen & Oney, CHI 2023) places each student on a 2D map
  of their problem-solving approach. It surfaced more student problems than a
  baseline, but its position on the map comes from code embeddings (CodeBERT).
  That axis has no obvious meaning to a lecturer glancing at it mid-lecture,
  and it would need a second clustering pipeline next to `aggregation.py`.
- **Codeopticon** (Guo, UIST 2015) shows one tile per learner and keeps
  reshuffling the tiles so the most active learners stay in view. It works for
  a tutor whose whole job is monitoring. For a lecturer who is also teaching,
  constant reordering is exactly the kind of visual disturbance the
  supervisors want to avoid.
- **OverCode** (Glassman et al., TOCHI 2015) clusters solutions after the
  fact. That is closer to our "Common issues" card than to live progress.
- **Teacher-dashboard studies** (e.g. Dey et al., AIED 2022, on classroom
  orchestration) report that dashboards fail when they show static or
  non-actionable information. They recommend showing both the class level and
  the individual level, with the teacher choosing how much detail to see.
- **Spark** (arXiv 2026) points out that earlier live dashboards use fixed data
  views. That supports keeping our view small and focused, without trying to
  make it configurable.

## Decision

The "Submission progress" card is now **Class progress**, with two layers:

1. **Always visible: one stacked bar.** Each student counts once, by their
   *best result so far* (correct / partial / incorrect / error), plus a grey
   "not yet submitted" segment when the question has `expected_students`.
   Below it is a legend with counts, so the bar can be read at a glance from a
   distance.
2. **Collapsible: one row per student** with a small square for every attempt,
   oldest first, coloured by verdict. Hovering a square shows the attempt
   number, time, tests passed and error type. The best score sits next to the
   name. The patterns lecturers care about are visible without opening code:
   a long run of red (stuck), red turning amber then green (getting there), a
   single attempt and silence (gave up?).

Choices made to keep it calm and simple:

- **Rows don't reorder on every poll.** Students sit in two alphabetical groups,
  *Still working* and *Solved*. A student moves exactly once, when they solve
  it, and that is the move worth noticing.
- **No animation, no time axis.** Squares are ordered by attempt rather than
  placed on a clock, so the chart doesn't drift or rescale while the lecturer
  is talking.
- **Collapsed by default, remembered per browser.** The per-student rows show
  names, and this dashboard often ends up on the projector. The class-level
  bar shows no names and stays visible either way.
- **No new endpoint.** Everything is derived from the submissions the page
  already polls every 3 seconds.
- **Colour.** The verdict-pill colours are too close (amber vs red) to tell
  apart at square size. The chart therefore uses its own re-stepped status
  colours (`#2e7d32`, `#c9a227`, `#b3453a`), checked for colour-blind
  separation. "Error" also gets a diagonal hatch, so it never depends on
  colour alone. The amber has low contrast against white, which the legend
  counts and the hover text make up for.

## Alternatives considered and not taken

- **Line or area chart of class state over time:** good for a post-lecture
  review, but it moves on every poll and needs a time axis. It answers "how
  did the class move" rather than "who needs me now".
- **Sankey diagram of verdict transitions:** informative, but heavy to read
  mid-lecture.
- **Heatmap with a fixed column per attempt:** the same information as the
  strips, but students with one attempt leave a mostly empty grid.

## Known limitations

- "Not yet submitted" in the bar is still a typed-in number. While a task
  runs, students who *joined* but haven't submitted do get rows (from the
  join table, see the activity section below). Students who never joined
  remain invisible, because there is still no roster.
- "Best result so far" hides a student who solved it and then submitted
  something broken. The strip still shows it, but the bar doesn't.
- Strips are cut to the latest 20 attempts, with a "+N" marker in front.
- With very large classes the student list scrolls (capped height). Grouping
  or filtering would be the next step if that becomes a problem in a pilot.
- The "Everyone has submitted" / "N more than expected" line under the old
  bar was dropped. The headline count and the legend's "not yet submitted"
  count cover it.

## Activity and idle nudges (2026-10-15, follow-up)

Supervisors' follow-up: the lecturer should also see whether students are
*actually typing*, i.e. who is trying and who has dropped off, and an idle
student should get a small nudge. They mentioned a VS Code extension.

**Editor.** A real VS Code extension would mean an install on every student
machine and a second submit path, so instead the student page's text box is
now **Monaco**, the editor VS Code is built on, running in the browser. It
gives syntax highlighting, line numbers and auto-indent, and its change
events are the activity signal. Autocomplete is switched off (it would
suggest code during an exercise). Monaco is bundled locally rather than
loaded from a CDN, so a weak lecture-hall network can't take it down, and
it's lazy-loaded, so the join and waiting screens stay small.

**Signal.** While a task runs, the student page sends a heartbeat every 10s
(`POST /api/lecture/activity`) that says only *whether* they typed since the
last one. The code itself is never sent, which keeps this easy to describe in
an ethics/consent form. The server stamps all times with its own clock and
keeps one row per student per question (`student_activity`).

**Statuses shown to the lecturer** (`GET /api/lecturer/questions/{id}/activity`):

- *active*: has typed within the idle threshold.
- *idle*: the editor is open, but no typing for at least the threshold
  (shown as e.g. "idle 4m").
- *away*: no heartbeat for 30s (tab closed, laptop asleep, offline), or
  joined but never opened the task.

In the Class progress card, a summary line ("N active · N idle · N away, of
those not solved yet") sits under the bar. When the card is expanded, an
**Idle or away** group is listed first, then *Working*, then *Solved*.
Students only change group when their state actually changes. Activity is
encoded with navy shapes (filled / ring / faint dot), not status colours:
typing isn't good or bad, and the verdict colours are already in use.
Solved students show no activity, since their editor has closed. Activity is
hidden once time is up, because everyone would read "away".

**Nudge.** Automatic, configured per question on the setup page ("Nudge
idle students after (minutes)", default 3, 0 = off). When a heartbeat finds
the student idle past the threshold, the reply carries a nudge, shown as a
calm card above the editor that disappears when they type or click "Got it".
Rules:

- Once per idle stretch. Typing resets it.
- Never after time's up.
- Never for a student who already solved the task.

The text is deliberately generic and answer-free (tier-0 scaffolds: work the
example by hand, write just the input-reading part and submit to see which
tests pass, put your hand up). The lecturer sees a small "nudged" tag on that
student's row.

### Activity limitations

- A student who switches to another tab keeps sending heartbeats (without
  typing), so they read as *idle*, not *away*. Chrome only slows background
  timers to once a minute after a tab has been hidden for 5 minutes ("intensive
  throttling", Chrome 88+), and only then do they drop to *away*. So *away*
  means the tab was closed, the laptop slept, the network dropped, or the
  student has been elsewhere for 5+ minutes. It doesn't always mean they gave
  up. A nudge can arrive while they're in another tab; they see it when they
  come back.
- Idle is measured as "no keystrokes". Thinking, reading the prompt or
  working on paper also count as idle. That's why the nudge is phrased as an
  offer, not a warning, and why the lecturer sees "idle 4m" rather than a
  judgement.
- The student's name is fixed after joining (shown as "Joined as", not
  editable), so submissions, heartbeats and the lecturer's rows can't split
  across two spellings. Fixing a typo means re-joining from a new tab.
- Nudge effectiveness (does it bring idle students back?) is unmeasured.
  `student_activity` keeps `nudged_at`/`nudge_count`/`last_edit_at`, enough to
  check in a pilot whether typing resumes after a nudge.

## End-of-lecture summary (2026-10-15, follow-up)

The post-lecture summary (`lecturer.html?lecture_id=`) now shows the same
Class progress chart for every task: the bar, the legend and the collapsible
per-student attempt strips. Activity is left out, because it is meaningless
once the lecture is over. The chart replaces the summary table's
verdict-pill column. That column counted each student's *latest* result,
while the chart counts their *best*, so keeping both would have shown two
different breakdowns of the same task side by side. The task title, the
submitted count and "View task →" stay as each task's header row.
