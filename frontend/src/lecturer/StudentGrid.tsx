import { useState } from "react";
import type { StudentActivity, SubmissionRow, Verdict } from "../shared/types";
import { LABEL, activityText, activityTitle, attemptTitle, buildTracks, isSolved, verdictOf } from "./studentTracks";
import type { StudentTrack } from "./studentTracks";
import { SubmissionDetail } from "./ExampleBlock";

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
const GROUPS: { key: Group; title: string }[] = [
  { key: "error", title: "Errors" },
  { key: "incorrect", title: "Wrong" },
  { key: "partially_correct", title: "Partial" },
  { key: "none", title: "No submission" },
  { key: "correct", title: "Solved" },
];

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
    <span className="roster-bars" aria-hidden="true">
      {hidden > 0 && <span className="roster-bars-more">+{hidden}</span>}
      {attempts.slice(hidden).map((s) => {
        const verdict = verdictOf(s);
        const share = s.tests_total ? s.tests_passed / s.tests_total : 0;
        const height = verdict === "error" ? BAR_HEIGHT : Math.max(2, Math.round(share * BAR_HEIGHT));
        return <span key={s.id} className={`roster-bar roster-bar-${verdict}`} style={{ height }} />;
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
    <div className="card" id="students-card">
      <div className="roster-head">
        <h2>Students</h2>
        <span className="roster-totals">
          {tracks.length} students · {subs.length} attempts
        </span>
        {tracks.length > 0 && (
          <button className="roster-names-toggle" aria-pressed={showNames} onClick={toggleNames}>
            {showNames ? "Hide names" : "Show names"}
          </button>
        )}
      </div>

      {tracks.length === 0 && <div className="card-empty">No one yet.</div>}

      {GROUPS.map(({ key, title }) => {
        const members = tracks.filter((t) => groupOf(t) === key);
        if (members.length === 0) return null;
        return (
          <section key={key} className={`roster-group roster-group-${key}`}>
            <h3>
              {title}
              <span className="roster-group-count">{members.length}</span>
            </h3>
            <ul className="roster-list">
              {members.map((t) => {
                const a = activity && !isSolved(t) ? t.activity : null;
                // "Away" is most students most of the time -- the top strip
                // counts them; a dot on every line would just be noise.
                const dot = a && a.status !== "away" ? a : null;
                return (
                  <li key={t.name}>
                    <button
                      className="roster-entry"
                      aria-pressed={selected === t.name}
                      onClick={() => select(t.name)}
                      title={
                        `${label(t)}: ` +
                        (t.best ? `best ${LABEL[verdictOf(t.best)]}, ${t.attempts.length} attempt(s)` : "no attempts yet") +
                        (a ? ` · ${activityTitle(a)}` : "")
                      }
                    >
                      <span className="roster-name">
                        {dot && <span className={`roster-act cp-act-${dot.status}`} aria-label={activityText(dot)} />}
                        {label(t)}
                      </span>
                      <AttemptBars attempts={t.attempts} />
                      {t.best && (
                        <span className="roster-score">
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
        <div className="roster-detail">
          <div className="roster-detail-head">
            <strong>{label(track)}</strong>
            {track.attempts.length > 0 && (
              <span className="roster-attempts" role="group" aria-label="Attempts">
                {track.attempts.map((s) => (
                  <button
                    key={s.id}
                    className={`roster-attempt roster-attempt-${verdictOf(s)}`}
                    aria-pressed={shownSub?.id === s.id}
                    title={attemptTitle(s)}
                    onClick={() => setSelectedAttempt(s.id)}
                  >
                    {s.attempt_number}
                  </button>
                ))}
              </span>
            )}
            <button className="roster-close" onClick={() => setSelected(null)}>
              Close
            </button>
          </div>
          {shownSub ? <SubmissionDetail sub={shownSub} /> : <div className="card-empty">No attempts yet.</div>}
        </div>
      )}
    </div>
  );
}
