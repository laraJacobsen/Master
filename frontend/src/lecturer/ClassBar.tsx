import type { Verdict } from "../shared/types";
import { LABEL, ORDER, verdictOf } from "./studentTracks";
import type { StudentTrack } from "./studentTracks";
import { HERO_FILL } from "../shared/verdictStyles";
import { cx } from "../shared/cx";

export interface ClassBarProps {
  tracks: StudentTrack[];
  expected: number | null;
}

// Segments narrower than this share of the bar don't get a number inside;
// the legend underneath still has it.
const LABEL_MIN_SHARE = 0.045;

// One wide bar of every student's best result so far (plus whoever hasn't
// submitted when a class size is set). Counts sit inside the segments.
export function ClassBar({ tracks, expected }: ClassBarProps) {
  const withResult = tracks.filter((t) => t.best);
  const counts = Object.fromEntries(
    ORDER.map((v) => [v, withResult.filter((t) => t.best && verdictOf(t.best) === v).length]),
  ) as Record<Verdict, number>;
  const notSubmitted = expected != null ? Math.max(0, expected - withResult.length) : 0;
  const total = withResult.length + notSubmitted;

  const segments: Array<[Verdict | "none", number, string]> = [
    ...ORDER.filter((v) => counts[v] > 0).map((v) => [v, counts[v], LABEL[v]] as [Verdict, number, string]),
    ...(notSubmitted > 0 ? [["none", notSubmitted, "not yet submitted"] as ["none", number, string]] : []),
  ];

  return (
    <div>
      <div
        className="flex h-14 gap-1 overflow-hidden rounded-lg"
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
