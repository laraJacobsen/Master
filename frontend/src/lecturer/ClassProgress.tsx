import { useState } from "react";
import type { ActivityStatus, StudentActivity, SubmissionRow, Verdict } from "../shared/types";
import {
  ACTIVITY_LABEL,
  LABEL,
  ORDER,
  activityText,
  activityTitle,
  attemptTitle,
  buildTracks,
  isSolved,
  verdictOf,
} from "./studentTracks";
import type { StudentTrack } from "./studentTracks";

// Class progress visualization for the live dashboard (see
// docs/decisions/class-progress-visualization-decision.md). Two layers:
//   1. Always visible: one stacked bar of every student's best result so far
//      (plus the not-yet-submitted remainder when a class size is set), and
//      while the task runs, how many unsolved students are active/idle/away
//      -- the at-a-glance "where is the class" signal.
//   2. Collapsible: one row per student with their activity and a square per
//      attempt, coloured by verdict, so "fell off", repeated errors and
//      progress toward "correct" are visible per student without opening code.
// Built from data the dashboard already polls, plus the activity heartbeat.

// Long attempt strips are cut to their most recent squares so one very busy
// student can't stretch the row; the cut is shown as "+N".
const MAX_SQUARES = 20;

const OPEN_KEY = "lecturer.classProgress.open";

function readOpen(): boolean {
  try {
    return window.localStorage.getItem(OPEN_KEY) === "1";
  } catch {
    return false;
  }
}

function StudentRow({ track, showActivity }: { track: StudentTrack; showActivity: boolean }) {
  const hidden = Math.max(0, track.attempts.length - MAX_SQUARES);
  const shown = track.attempts.slice(hidden);
  // Solved students are done -- their editor closes, so "away" would be noise.
  const a = showActivity && !isSolved(track) ? track.activity : null;
  return (
    <li className={showActivity ? "cp-row cp-row-activity" : "cp-row"}>
      <span className="cp-name" title={track.name}>
        {track.name}
      </span>
      <span className="cp-score" title="Best result so far">
        {track.best ? `${track.best.tests_passed}/${track.best.tests_total}` : "–"}
      </span>
      {showActivity && (
        <span className={a ? `cp-activity cp-act-${a.status}` : "cp-activity"} title={a ? activityTitle(a) : undefined}>
          {a && (
            <>
              <span className="cp-act-dot" aria-hidden="true" />
              {activityText(a)}
              {a.nudged && <span className="cp-nudged">nudged</span>}
            </>
          )}
        </span>
      )}
      <span
        className="cp-strip"
        role="img"
        aria-label={
          track.attempts.length
            ? `${track.name}: ${track.attempts.map((s) => LABEL[verdictOf(s)]).join(", ")}`
            : `${track.name}: no attempts yet`
        }
      >
        {hidden > 0 && <span className="cp-more">+{hidden}</span>}
        {shown.map((s) => (
          <span key={s.id} className={`cp-sq cp-${verdictOf(s)}`} title={attemptTitle(s)} />
        ))}
      </span>
    </li>
  );
}

function Group({ title, tracks, showActivity }: { title: string; tracks: StudentTrack[]; showActivity: boolean }) {
  if (tracks.length === 0) return null;
  return (
    <>
      <h3 className="cp-group">
        {title} ({tracks.length})
      </h3>
      <ul className="cp-rows">
        {tracks.map((t) => (
          <StudentRow key={t.name} track={t} showActivity={showActivity} />
        ))}
      </ul>
    </>
  );
}

export function ClassProgress({
  subs,
  expected,
  activity,
  finished = false,
  showStudents = true,
}: {
  subs: SubmissionRow[];
  expected: number | null;
  // Null when activity doesn't apply (task not running) -- hides it entirely.
  activity: StudentActivity[] | null;
  // The task is over (end-of-lecture summary) -- wording only.
  finished?: boolean;
  // The live dashboard shows students in its own tile grid (StudentGrid) --
  // there this is just the summary bar, legend and activity counts.
  showStudents?: boolean;
}) {
  // Collapsed by default: the per-student rows carry names, and this
  // dashboard is often on the projector. The summary above stays visible
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

  const showActivity = activity != null;
  const tracks = buildTracks(subs, activity);
  const submitted = tracks.filter((t) => t.best);
  const counts = Object.fromEntries(
    ORDER.map((v) => [v, submitted.filter((t) => t.best && verdictOf(t.best) === v).length]),
  ) as Record<Verdict, number>;
  const notSubmitted = expected != null ? Math.max(0, expected - submitted.length) : 0;
  const total = submitted.length + notSubmitted;

  const solved = tracks.filter(isSolved);
  const unsolved = tracks.filter((t) => !isSolved(t));
  // While the task runs, students who stopped typing or dropped off come
  // first -- that's the group the lecturer might walk over to. A student
  // only changes group when their state actually changes.
  const needsAttention = showActivity
    ? unsolved.filter((t) => !t.activity || t.activity.status !== "active")
    : [];
  const working = showActivity ? unsolved.filter((t) => t.activity?.status === "active") : unsolved;
  const activityCounts = Object.fromEntries(
    (["active", "idle", "away"] as ActivityStatus[]).map((st) => [
      st,
      unsolved.filter((t) => (t.activity?.status ?? "away") === st).length,
    ]),
  ) as Record<ActivityStatus, number>;

  return (
    <div className="class-progress">
      {total > 0 && (
        <div className="cp-bar" role="img" aria-label="Best result per student" title="Each student's best result">
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
              title={`${notSubmitted} ${finished ? "didn't submit" : "not yet submitted"}`}
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
            {notSubmitted} {finished ? "didn't submit" : "not yet submitted"}
          </li>
        )}
      </ul>

      {showActivity && unsolved.length > 0 && (
        <ul
          className="cp-legend cp-activity-summary"
          aria-label="Students who haven't solved it, by activity"
          title="Students who haven't solved it yet. Idle: no typing for a few minutes. Away: editor not open."
        >
          {(["active", "idle", "away"] as ActivityStatus[]).map((st) => (
            <li key={st} className={`cp-act-${st}`}>
              <span className="cp-act-dot" aria-hidden="true" />
              {activityCounts[st]} {ACTIVITY_LABEL[st]}
            </li>
          ))}
        </ul>
      )}

      {showStudents && tracks.length > 0 && (
        <button className="view-example-btn cp-toggle" aria-expanded={open} onClick={toggle}>
          {open ? "▾ Hide students" : `▸ Show students (${tracks.length})`}
        </button>
      )}
      {showStudents && open && tracks.length > 0 && (
        <div className="cp-students">
          <Group title="Idle or away" tracks={needsAttention} showActivity={showActivity} />
          <Group title={showActivity ? "Working" : "Not solved"} tracks={working} showActivity={showActivity} />
          <Group title="Solved" tracks={solved} showActivity={showActivity} />
        </div>
      )}
    </div>
  );
}
