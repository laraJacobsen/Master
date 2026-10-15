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

- "Not yet submitted" is still only a number. There is no roster, so
  non-submitters have no rows (same limitation as the earlier counter).
- "Best result so far" hides a student who solved it and then submitted
  something broken. The strip still shows it, but the bar doesn't.
- Strips are cut to the latest 20 attempts, with a "+N" marker in front.
- With very large classes the student list scrolls (capped height). Grouping
  or filtering would be the next step if that becomes a problem in a pilot.
- The "Everyone has submitted" / "N more than expected" line under the old
  bar was dropped. The headline count and the legend's "not yet submitted"
  count cover it.
