import { useState } from "react";
import type { SubmissionRow, Verdict } from "../shared/types";

// Class progress visualization for the live dashboard (see
// feedback-research/class-progress-visualization-decision.md). Two layers:
//   1. Always visible: one stacked bar of every student's best result so far
//      (plus the not-yet-submitted remainder when a class size is set) -- the
//      at-a-glance "where is the class" signal.
//   2. Collapsible: one row per student with a square per attempt, coloured
//      by verdict, so repeated errors and progress toward "correct" are
//      visible per student without opening any code.
// Built entirely from the submissions the dashboard already polls -- no extra
// endpoint.

const ORDER: Verdict[] = ["correct", "partially_correct", "incorrect", "error"];

const LABEL: Record<Verdict, string> = {
  correct: "correct",
  partially_correct: "partial",
  incorrect: "incorrect",
  error: "error",
};

// Higher is better -- picks each student's best attempt for the summary bar.
const RANK: Record<Verdict, number> = { error: 0, incorrect: 1, partially_correct: 2, correct: 3 };

// Long attempt strips are cut to their most recent squares so one very busy
// student can't stretch the row; the cut is shown as "+N".
const MAX_SQUARES = 20;

const OPEN_KEY = "lecturer.classProgress.open";

interface StudentTrack {
  name: string;
  attempts: SubmissionRow[]; // oldest first
  best: SubmissionRow;
}

function verdictOf(s: SubmissionRow): Verdict {
  return s.verdict ?? "error";
}

function isBetter(a: SubmissionRow, b: SubmissionRow): boolean {
  const ra = RANK[verdictOf(a)];
  const rb = RANK[verdictOf(b)];
  if (ra !== rb) return ra > rb;
  return a.tests_passed >= b.tests_passed; // ties go to the later attempt
}

// Grouped into "still working" and "solved", each alphabetical, rather than
// sorted by attempts or score: rows then stay put across polls, and a student
// only moves once -- when they solve it, which is the move worth noticing.
function buildTracks(subs: SubmissionRow[]): StudentTrack[] {
  const byName = new Map<string, SubmissionRow[]>();
  for (const sub of [...subs].sort((a, b) => a.id - b.id)) {
    byName.set(sub.student_name, [...(byName.get(sub.student_name) ?? []), sub]);
  }
  return [...byName.entries()]
    .map(([name, attempts]) => ({
      name,
      attempts,
      best: attempts.reduce((best, s) => (isBetter(s, best) ? s : best)),
    }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

function attemptTitle(s: SubmissionRow): string {
  const time = (s.created_at || "").split(" ")[1] || s.created_at;
  const result = s.rejection_reason
    ? `rejected (${s.rejection_reason})`
    : `${LABEL[verdictOf(s)]}, ${s.tests_passed}/${s.tests_total} tests`;
  const kind = s.error_type && s.error_type !== "none" ? ` · ${s.error_type}` : "";
  return `Attempt ${s.attempt_number} at ${time}: ${result}${kind}`;
}

function readOpen(): boolean {
  try {
    return window.localStorage.getItem(OPEN_KEY) === "1";
  } catch {
    return false;
  }
}

function StudentRow({ track }: { track: StudentTrack }) {
  const hidden = Math.max(0, track.attempts.length - MAX_SQUARES);
  const shown = track.attempts.slice(hidden);
  return (
    <li className="cp-row">
      <span className="cp-name" title={track.name}>
        {track.name}
      </span>
      <span className="cp-score" title="Best result so far">
        {track.best.tests_passed}/{track.best.tests_total}
      </span>
      <span
        className="cp-strip"
        role="img"
        aria-label={`${track.name}: ${track.attempts.map((s) => LABEL[verdictOf(s)]).join(", ")}`}
      >
        {hidden > 0 && <span className="cp-more">+{hidden}</span>}
        {shown.map((s) => (
          <span key={s.id} className={`cp-sq cp-${verdictOf(s)}`} title={attemptTitle(s)} />
        ))}
      </span>
    </li>
  );
}

export function ClassProgress({ subs, expected }: { subs: SubmissionRow[]; expected: number | null }) {
  // Collapsed by default: the per-student rows carry names, and this
  // dashboard is often on the projector. The summary bar above stays visible
  // either way. Remembered per browser so it doesn't reset every task.
  const [open, setOpen] = useState(readOpen);

  function toggle() {
    setOpen((prev) => {
      try {
        window.localStorage.setItem(OPEN_KEY, prev ? "0" : "1");
      } catch {
        // Storage blocked -- the toggle still works for this page view.
      }
      return !prev;
    });
  }

  const tracks = buildTracks(subs);
  const counts = Object.fromEntries(
    ORDER.map((v) => [v, tracks.filter((t) => verdictOf(t.best) === v).length]),
  ) as Record<Verdict, number>;
  const notSubmitted = expected != null ? Math.max(0, expected - tracks.length) : 0;
  const total = tracks.length + notSubmitted;
  const working = tracks.filter((t) => verdictOf(t.best) !== "correct");
  const solved = tracks.filter((t) => verdictOf(t.best) === "correct");

  return (
    <div className="class-progress">
      {total > 0 && (
        <div className="cp-bar" role="img" aria-label="Best result so far per student">
          {ORDER.filter((v) => counts[v] > 0).map((v) => (
            <span
              key={v}
              className={`cp-seg cp-${v}`}
              style={{ flexGrow: counts[v] }}
              title={`${counts[v]} ${LABEL[v]}`}
            />
          ))}
          {notSubmitted > 0 && (
            <span
              className="cp-seg cp-none"
              style={{ flexGrow: notSubmitted }}
              title={`${notSubmitted} not yet submitted`}
            />
          )}
        </div>
      )}
      <ul className="cp-legend">
        {ORDER.map((v) => (
          <li key={v}>
            <span className={`cp-sq cp-${v}`} aria-hidden="true" />
            {counts[v]} {LABEL[v]}
          </li>
        ))}
        {expected != null && (
          <li>
            <span className="cp-sq cp-none" aria-hidden="true" />
            {notSubmitted} not yet submitted
          </li>
        )}
      </ul>
      <div className="cp-caption">Best result so far per student.</div>

      {tracks.length > 0 && (
        <button className="view-example-btn cp-toggle" aria-expanded={open} onClick={toggle}>
          {open ? "▾ Hide students" : `▸ Show students (${tracks.length})`}
        </button>
      )}
      {open && tracks.length > 0 && (
        <div className="cp-students">
          <div className="cp-caption">One square per attempt, oldest on the left. Hover a square for details.</div>
          {working.length > 0 && (
            <>
              <h3 className="cp-group">Still working ({working.length})</h3>
              <ul className="cp-rows">
                {working.map((t) => (
                  <StudentRow key={t.name} track={t} />
                ))}
              </ul>
            </>
          )}
          {solved.length > 0 && (
            <>
              <h3 className="cp-group">Solved ({solved.length})</h3>
              <ul className="cp-rows">
                {solved.map((t) => (
                  <StudentRow key={t.name} track={t} />
                ))}
              </ul>
            </>
          )}
        </div>
      )}
    </div>
  );
}
