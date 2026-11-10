import type { ActivityStatus, Verdict } from "../shared/types";
import { ACTIVITY_LABEL, LABEL, ORDER, isSolved, verdictOf } from "./studentTracks";
import type { StudentTrack } from "./studentTracks";
import { ActivityDot } from "./ClassProgress";
import { HERO_FILL } from "../shared/verdictStyles";
import { cx } from "../shared/cx";

export interface ClassBarProps {
  tracks: StudentTrack[];
  submitted: number;
  expected: number | null;
  // Activity only means something while students can still type.
  showActivity: boolean;
}

// Segments narrower than this share of the bar don't get a number inside;
// the legend underneath still has it.
const LABEL_MIN_SHARE = 0.045;

// The live dashboard's centrepiece: one wide bar of every student's best
// result so far (plus whoever hasn't submitted when a class size is set),
// readable from across the room. Counts sit inside the segments.
export function ClassBar({ tracks, submitted, expected, showActivity }: ClassBarProps) {
  const withResult = tracks.filter((t) => t.best);
  const counts = Object.fromEntries(
    ORDER.map((v) => [v, withResult.filter((t) => t.best && verdictOf(t.best) === v).length]),
  ) as Record<Verdict, number>;
  const notSubmitted = expected != null ? Math.max(0, expected - withResult.length) : 0;
  const total = withResult.length + notSubmitted;

  const unsolved = tracks.filter((t) => !isSolved(t));
  const activityCounts = (["active", "idle", "away"] as ActivityStatus[]).map(
    (st) => [st, unsolved.filter((t) => (t.activity?.status ?? "away") === st).length] as const,
  );

  const segments: Array<[Verdict | "none", number, string]> = [
    ...ORDER.filter((v) => counts[v] > 0).map((v) => [v, counts[v], LABEL[v]] as [Verdict, number, string]),
    ...(notSubmitted > 0 ? [["none", notSubmitted, "not yet submitted"] as ["none", number, string]] : []),
  ];

  return (
    <div>
      <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-3">
        <p className="flex items-baseline gap-2 text-zinc-500">
          <span className="font-mono text-4xl font-semibold tracking-tight text-zinc-950 tabular-nums">{submitted}</span>
          {expected != null && submitted <= expected && (
            <span className="font-mono text-xl text-zinc-400 tabular-nums">/ {expected}</span>
          )}
          <span className="ml-1 text-sm">
            submitted
            {expected != null && submitted > expected && ` · more than the ${expected} expected`}
          </span>
        </p>
        {showActivity && unsolved.length > 0 && (
          <ul
            className="flex gap-5 text-[13px] text-zinc-500"
            aria-label="Students who haven't solved it, by activity"
            title="Students who haven't solved it yet. Idle: no typing for a few minutes. Away: editor not open."
          >
            {activityCounts.map(([st, n]) => (
              <li key={st} className={cx("flex items-center gap-1.5", st === "idle" && n > 0 && "font-semibold text-zinc-900")}>
                <ActivityDot status={st} />
                <span className="font-mono tabular-nums">{n}</span> {ACTIVITY_LABEL[st]}
              </li>
            ))}
          </ul>
        )}
      </div>

      <div
        className="mt-5 flex h-14 gap-1 overflow-hidden rounded-lg"
        role="img"
        aria-label={
          total
            ? segments.map(([, n, label]) => `${n} ${label}`).join(", ")
            : "No submissions yet"
        }
      >
        {total === 0 ? (
          <div className="flex flex-1 items-center rounded-lg border border-dashed border-zinc-300 px-5 text-sm text-zinc-400">
            Waiting for the first submission
          </div>
        ) : (
          segments.map(([kind, n, label]) => (
            <div
              key={kind}
              className={cx(
                "flex min-w-1.5 basis-0 items-center overflow-hidden px-3 transition-[flex-grow] duration-700 ease-out first:rounded-l-lg last:rounded-r-lg",
                HERO_FILL[kind],
              )}
              style={{ flexGrow: n }}
              title={`${n} ${label}`}
            >
              {n / total >= LABEL_MIN_SHARE && (
                <span className="font-mono text-lg font-semibold tabular-nums">{n}</span>
              )}
            </div>
          ))
        )}
      </div>

      <ul className="mt-3 flex flex-wrap gap-x-5 gap-y-1 text-[13px] text-zinc-500">
        {ORDER.map((v) => (
          <li key={v} className={cx("flex items-center gap-1.5", counts[v] === 0 && "opacity-50")}>
            <span className={cx("size-2.5 rounded-[3px]", HERO_FILL[v])} aria-hidden="true" />
            {LABEL[v]}
          </li>
        ))}
        {expected != null && (
          <li className="flex items-center gap-1.5">
            <span className={cx("size-2.5 rounded-[3px] border border-zinc-300", HERO_FILL.none)} aria-hidden="true" />
            not yet submitted
          </li>
        )}
      </ul>
    </div>
  );
}
