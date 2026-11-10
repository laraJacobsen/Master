import { useState } from "react";
import type { StudentActivity, SubmissionRow, Verdict } from "../shared/types";
import { LABEL, activityText, activityTitle, attemptTitle, buildTracks, isSolved, verdictOf } from "./studentTracks";
import type { StudentTrack } from "./studentTracks";
import { SubmissionDetail } from "./ExampleBlock";
import { ActivityDot } from "./ClassProgress";
import { VERDICT_BORDER } from "./verdictStyles";
import { Button, Card } from "../shared/ui";
import { cx } from "../shared/cx";

// The live dashboard's per-student view, laid out like a gradebook: students
// grouped under their best result (worst first), one line each -- name, a
// tiny bar per attempt (height = tests passed, so "getting closer" and "stuck"
// read at a glance), and the best score. Replaces the old one-row-per-attempt
// submissions table, which grew without bound on a long task. Clicking a
// student opens their attempts and code underneath.

// Only the latest attempts get a bar, so a busy student can't widen their line.
const MAX_BARS = 10;
const BAR_HEIGHT = 14;

// Names are hidden by default (numbered instead) -- this dashboard can end
// up on a shared screen. Remembered per browser so it doesn't reset every task.
const NAMES_KEY = "lecturer.studentGrid.names";

type Group = Verdict | "none";

// Worst first: the students worth a look sit at the top.
const GROUPS: { key: Group; title: string; tone: string }[] = [
  { key: "error", title: "Errors", tone: "text-red-700" },
  { key: "incorrect", title: "Wrong", tone: "text-red-700" },
  { key: "partially_correct", title: "Partial", tone: "text-zinc-900" },
  { key: "none", title: "No submission", tone: "text-zinc-900" },
  { key: "correct", title: "Solved", tone: "text-emerald-700" },
];

// Roster bars: solid for a run, hollow outline for an error (didn't run).
const BAR_FILL: Record<Verdict, string> = {
  correct: "bg-emerald-600",
  partially_correct: "bg-amber-400",
  incorrect: "bg-red-600",
  error: "shadow-[inset_0_0_0_1px_var(--color-red-600)]",
};

function readShowNames(): boolean {
  try {
    return window.localStorage.getItem(NAMES_KEY) === "1";
  } catch {
    return false;
  }
}

function groupOf(t: StudentTrack): Group {
  return t.best ? verdictOf(t.best) : "none";
}

export interface AttemptBarsProps {
  attempts: SubmissionRow[];
}

// One bar per attempt, oldest left. An error (the program didn't run) is a
// hollow full-height bar, so it can't be mistaken for "ran, passed nothing".
export function AttemptBars({ attempts }: AttemptBarsProps) {
  const hidden = Math.max(0, attempts.length - MAX_BARS);
  return (
    <span className="flex h-3.5 items-end gap-0.5" aria-hidden="true">
      {hidden > 0 && <span className="mr-0.5 font-mono text-[10px] text-zinc-500">+{hidden}</span>}
      {attempts.slice(hidden).map((s) => {
        const verdict = verdictOf(s);
        const share = s.tests_total ? s.tests_passed / s.tests_total : 0;
        const height = verdict === "error" ? BAR_HEIGHT : Math.max(2, Math.round(share * BAR_HEIGHT));
        return <span key={s.id} className={cx("w-1 rounded-[1px]", BAR_FILL[verdict])} style={{ height }} />;
      })}
    </span>
  );
}

export interface StudentGridProps {
  subs: SubmissionRow[];
  // Null once the task isn't running -- activity would read "away" for everyone.
  activity: StudentActivity[] | null;
}

export function StudentGrid({ subs, activity }: StudentGridProps) {
  const [showNames, setShowNames] = useState(readShowNames);
  const [selected, setSelected] = useState<string | null>(null);
  const [selectedAttempt, setSelectedAttempt] = useState<number | null>(null);

  function toggleNames() {
    setShowNames((prev) => {
      try {
        window.localStorage.setItem(NAMES_KEY, prev ? "0" : "1");
      } catch {
        // Storage blocked -- the toggle still works for this page view.
      }
      return !prev;
    });
  }

  // Alphabetical, so a student's number (names hidden) and place in their
  // group only change when they move to another group.
  const tracks = buildTracks(subs, activity);
  const number = new Map(tracks.map((t, i) => [t.name, String(i + 1).padStart(2, "0")]));
  const label = (t: StudentTrack) => (showNames ? t.name : `#${number.get(t.name)}`);
  const track = tracks.find((t) => t.name === selected) ?? null;
  const shownSub = track
    ? track.attempts.find((s) => s.id === selectedAttempt) ?? track.attempts[track.attempts.length - 1] ?? null
    : null;

  function select(name: string) {
    setSelected((prev) => (prev === name ? null : name));
    setSelectedAttempt(null);
  }

  return (
    <Card>
      <div className="flex items-center gap-3">
        <h2 className="text-[15px] font-bold tracking-tight text-zinc-950">Students</h2>
        <span className="font-mono text-xs text-zinc-500">
          {tracks.length} students · {subs.length} attempts
        </span>
        {tracks.length > 0 && (
          <Button variant="secondary" size="sm" className="ml-auto" aria-pressed={showNames} onClick={toggleNames}>
            {showNames ? "Hide names" : "Show names"}
          </Button>
        )}
      </div>

      {tracks.length === 0 && <p className="mt-3 text-sm text-zinc-500">No one yet.</p>}

      {GROUPS.map(({ key, title, tone }) => {
        const members = tracks.filter((t) => groupOf(t) === key);
        if (members.length === 0) return null;
        return (
          <section key={key} className="mt-5">
            <h3
              className={cx(
                "mb-1 flex items-baseline gap-2 border-b border-zinc-200 pb-1.5 text-[13px] font-bold tracking-tight",
                tone,
              )}
            >
              {title}
              <span className="font-mono text-xs font-medium text-zinc-500">{members.length}</span>
            </h3>
            <ul className="grid grid-cols-[repeat(auto-fill,minmax(8.75rem,1fr))] gap-x-4">
              {members.map((t) => {
                const a = activity && !isSolved(t) ? t.activity : null;
                // "Away" is most students most of the time -- the top strip
                // counts them; a dot on every line would just be noise.
                const dot = a && a.status !== "away" ? a : null;
                const isSelected = selected === t.name;
                return (
                  <li key={t.name}>
                    <button
                      type="button"
                      className={cx(
                        "-mx-1.5 grid w-[calc(100%+0.75rem)] grid-cols-[1fr_auto_2.2rem] items-center gap-2 rounded-md px-1.5 py-1 text-left text-[13px] transition-colors",
                        "focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-zinc-900",
                        isSelected ? "bg-zinc-100 ring-1 ring-zinc-900 ring-inset" : "hover:bg-zinc-100",
                      )}
                      aria-pressed={isSelected}
                      onClick={() => select(t.name)}
                      title={
                        `${label(t)}: ` +
                        (t.best ? `best ${LABEL[verdictOf(t.best)]}, ${t.attempts.length} attempt(s)` : "no attempts yet") +
                        (a ? ` · ${activityTitle(a)}` : "")
                      }
                    >
                      <span
                        className={cx(
                          "flex min-w-0 items-center gap-1.5 truncate",
                          key === "none" ? "text-zinc-500" : "text-zinc-900",
                          !showNames && "font-mono text-xs",
                        )}
                      >
                        {dot && (
                          <span role="img" aria-label={activityText(dot)} className="flex">
                            <ActivityDot status={dot.status} />
                          </span>
                        )}
                        {label(t)}
                      </span>
                      <AttemptBars attempts={t.attempts} />
                      {t.best && (
                        <span className="text-right font-mono text-xs text-zinc-500 tabular-nums">
                          {t.best.tests_passed}/{t.best.tests_total}
                        </span>
                      )}
                    </button>
                  </li>
                );
              })}
            </ul>
          </section>
        );
      })}

      {track && (
        <div className="mt-5 animate-fade-in border-t border-zinc-200 pt-4 text-[13px]">
          <div className="mb-3 flex flex-wrap items-center gap-3">
            <strong className={cx("font-bold tracking-tight text-zinc-950", !showNames && "font-mono")}>
              {label(track)}
            </strong>
            {track.attempts.length > 0 && (
              <span className="flex flex-wrap gap-1" role="group" aria-label="Attempts">
                {track.attempts.map((s) => {
                  const pressed = shownSub?.id === s.id;
                  return (
                    <button
                      type="button"
                      key={s.id}
                      className={cx(
                        "min-w-7 rounded-md border border-b-[3px] px-1.5 py-0.5 font-mono text-xs font-semibold transition-colors",
                        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900",
                        VERDICT_BORDER[verdictOf(s)],
                        pressed
                          ? "border-x-zinc-900 border-t-zinc-900 bg-zinc-900 text-white"
                          : "border-x-zinc-200 border-t-zinc-200 bg-white text-zinc-900 hover:bg-zinc-100",
                      )}
                      aria-pressed={pressed}
                      title={attemptTitle(s)}
                      onClick={() => setSelectedAttempt(s.id)}
                    >
                      {s.attempt_number}
                    </button>
                  );
                })}
              </span>
            )}
            <Button variant="ghost" size="sm" className="ml-auto" onClick={() => setSelected(null)}>
              Close
            </Button>
          </div>
          {shownSub ? <SubmissionDetail sub={shownSub} /> : <p className="text-sm text-zinc-500">No attempts yet.</p>}
        </div>
      )}
    </Card>
  );
}
