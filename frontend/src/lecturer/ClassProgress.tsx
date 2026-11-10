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
import { ACTIVITY_DOT, VERDICT_FILL } from "../shared/verdictStyles";
import { Button } from "../shared/ui";
import { cx } from "../shared/cx";

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

export interface SquareProps {
  kind: Verdict | "none";
  title?: string;
}

function Square({ kind, title }: SquareProps) {
  return <span className={cx("inline-block size-3 flex-none rounded-[3px]", VERDICT_FILL[kind])} title={title} aria-hidden={title ? undefined : true} />;
}

export interface ActivityDotProps {
  status: ActivityStatus;
}

export function ActivityDot({ status }: ActivityDotProps) {
  return <span className={cx("inline-block size-2 flex-none rounded-[2px]", ACTIVITY_DOT[status])} aria-hidden="true" />;
}

export interface StudentRowProps {
  track: StudentTrack;
  showActivity: boolean;
}

function StudentRow({ track, showActivity }: StudentRowProps) {
  const hidden = Math.max(0, track.attempts.length - MAX_SQUARES);
  const shown = track.attempts.slice(hidden);
  // Solved students are done -- their editor closes, so "away" would be noise.
  const a = showActivity && !isSolved(track) ? track.activity : null;
  return (
    <li
      className={cx(
        "grid items-center gap-3 py-1 text-[13px]",
        showActivity
          ? "grid-cols-[5.5rem_2.5rem_1fr] sm:grid-cols-[minmax(6rem,10rem)_2.5rem_7.5rem_1fr]"
          : "grid-cols-[5.5rem_2.5rem_1fr] sm:grid-cols-[minmax(6rem,10rem)_2.5rem_1fr]",
      )}
    >
      <span className="truncate text-zinc-900" title={track.name}>
        {track.name}
      </span>
      <span className="font-mono text-xs text-zinc-500 tabular-nums" title="Best result so far">
        {track.best ? `${track.best.tests_passed}/${track.best.tests_total}` : "–"}
      </span>
      {showActivity && (
        <span
          className={cx(
            "flex items-center gap-1.5 whitespace-nowrap max-sm:col-start-2 max-sm:col-end-[-1]",
            a?.status === "idle" ? "font-semibold text-zinc-900" : "text-zinc-500",
          )}
          title={a ? activityTitle(a) : undefined}
        >
          {a && (
            <>
              <ActivityDot status={a.status} />
              {activityText(a)}
              {a.nudged && (
                <span className="rounded border border-zinc-200 px-1 text-[10px] font-normal text-zinc-500">nudged</span>
              )}
            </>
          )}
        </span>
      )}
      <span
        className="flex flex-wrap items-center gap-0.5 max-sm:col-start-2 max-sm:col-end-[-1]"
        role="img"
        aria-label={
          track.attempts.length
            ? `${track.name}: ${track.attempts.map((s) => LABEL[verdictOf(s)]).join(", ")}`
            : `${track.name}: no attempts yet`
        }
      >
        {hidden > 0 && <span className="mr-1 font-mono text-[11px] text-zinc-500">+{hidden}</span>}
        {shown.map((s) => (
          <Square key={s.id} kind={verdictOf(s)} title={attemptTitle(s)} />
        ))}
      </span>
    </li>
  );
}

export interface GroupProps {
  title: string;
  tracks: StudentTrack[];
  showActivity: boolean;
}

function Group({ title, tracks, showActivity }: GroupProps) {
  if (tracks.length === 0) return null;
  return (
    <>
      <h3 className="mt-4 mb-1 text-[11px] font-semibold tracking-[0.08em] text-zinc-500 uppercase first:mt-0">
        {title} <span className="font-mono">({tracks.length})</span>
      </h3>
      <ul>
        {tracks.map((t) => (
          <StudentRow key={t.name} track={t} showActivity={showActivity} />
        ))}
      </ul>
    </>
  );
}

export interface ClassProgressProps {
  subs: SubmissionRow[];
  expected: number | null;
  // Null when activity doesn't apply (task not running) -- hides it entirely.
  activity: StudentActivity[] | null;
  // The task is over (end-of-lecture summary) -- wording only.
  finished?: boolean;
  // The live dashboard shows students in its own roster (StudentGrid) --
  // there this is just the summary bar, legend and activity counts.
  showStudents?: boolean;
  /** Taller bar, for the live task strip. */
  large?: boolean;
}

export function ClassProgress({
  subs,
  expected,
  activity,
  finished = false,
  showStudents = true,
  large = false,
}: ClassProgressProps) {
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
    <div className="mt-2">
      {total > 0 && (
        <div
          className={cx("flex gap-0.5 overflow-hidden rounded-sm", large ? "h-3.5" : "h-3")}
          role="img"
          aria-label="Best result per student"
          title="Each student's best result"
        >
          {ORDER.filter((v) => counts[v] > 0).map((v) => (
            <span
              key={v}
              className={cx("min-w-1 basis-0 transition-[flex-grow] duration-500", VERDICT_FILL[v])}
              style={{ flexGrow: counts[v] }}
              title={`${counts[v]} ${LABEL[v]}`}
            />
          ))}
          {notSubmitted > 0 && (
            <span
              className={cx("min-w-1 basis-0 transition-[flex-grow] duration-500", VERDICT_FILL.none)}
              style={{ flexGrow: notSubmitted }}
              title={`${notSubmitted} ${finished ? "didn't submit" : "not yet submitted"}`}
            />
          )}
        </div>
      )}
      <ul className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-zinc-700">
        {ORDER.map((v) => (
          <li key={v} className="flex items-center gap-1.5">
            <Square kind={v} />
            <span className="font-mono text-zinc-950 tabular-nums">{counts[v]}</span> {LABEL[v]}
          </li>
        ))}
        {expected != null && (
          <li className="flex items-center gap-1.5">
            <Square kind="none" />
            <span className="font-mono text-zinc-950 tabular-nums">{notSubmitted}</span>{" "}
            {finished ? "didn't submit" : "not yet submitted"}
          </li>
        )}
      </ul>

      {showActivity && unsolved.length > 0 && (
        <ul
          className="mt-1.5 flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-zinc-500"
          aria-label="Students who haven't solved it, by activity"
          title="Students who haven't solved it yet. Idle: no typing for a few minutes. Away: editor not open."
        >
          {(["active", "idle", "away"] as ActivityStatus[]).map((st) => (
            <li key={st} className={cx("flex items-center gap-1.5", st === "idle" && "font-semibold text-zinc-900")}>
              <ActivityDot status={st} />
              <span className="font-mono tabular-nums">{activityCounts[st]}</span> {ACTIVITY_LABEL[st]}
            </li>
          ))}
        </ul>
      )}

      {showStudents && tracks.length > 0 && (
        <Button variant="secondary" size="sm" className="mt-3" aria-expanded={open} onClick={toggle}>
          <svg
            className={cx("size-3 transition-transform", open && "rotate-90")}
            viewBox="0 0 12 12"
            fill="none"
            aria-hidden="true"
          >
            <path d="M4.5 3l3 3-3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          {open ? "Hide students" : `Show students (${tracks.length})`}
        </Button>
      )}
      {showStudents && open && tracks.length > 0 && (
        <div className="mt-3 max-h-80 overflow-y-auto">
          <Group title="Idle or away" tracks={needsAttention} showActivity={showActivity} />
          <Group title={showActivity ? "Working" : "Not solved"} tracks={working} showActivity={showActivity} />
          <Group title="Solved" tracks={solved} showActivity={showActivity} />
        </div>
      )}
    </div>
  );
}
