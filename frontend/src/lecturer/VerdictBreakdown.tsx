import { useState } from "react";
import type { StudentActivity, SubmissionRow, Verdict } from "../shared/types";
import { LABEL, ORDER, verdictOf } from "./studentTracks";
import type { StudentTrack } from "./studentTracks";
import { ClassBar } from "./ClassBar";
import { StudentGrid } from "./StudentGrid";
import { HERO_FILL } from "../shared/verdictStyles";
import { Card } from "../shared/ui";
import { cx } from "../shared/cx";

export interface VerdictBreakdownProps {
  tracks: StudentTrack[];
  subs: SubmissionRow[];
  expected: number | null;
  // Null once the task isn't running.
  activity: StudentActivity[] | null;
}

// Each student's best result so far. Collapsed by default to one line of
// counts; expanding shows the big bar and the per-student tiles.
export function VerdictBreakdown({ tracks, subs, expected, activity }: VerdictBreakdownProps) {
  const [open, setOpen] = useState(false);
  const counts = Object.fromEntries(
    ORDER.map((v) => [v, tracks.filter((t) => t.best && verdictOf(t.best) === v).length]),
  ) as Record<Verdict, number>;

  return (
    <Card flush>
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className="flex w-full flex-wrap items-center gap-x-4 gap-y-2 rounded-xl px-5 py-4 text-left transition-colors hover:bg-zinc-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500 sm:px-6"
      >
        <h2 className="text-[15px] font-bold tracking-tight text-zinc-950">Verdict breakdown</h2>
        {!open && (
          <ul className="flex flex-wrap gap-x-4 gap-y-1 text-[13px] text-zinc-600">
            {ORDER.map((v) => (
              <li key={v} className={cx("flex items-center gap-1.5", counts[v] === 0 && "opacity-50")}>
                <span className={cx("size-2.5 rounded-[3px]", HERO_FILL[v])} aria-hidden="true" />
                <span className="font-mono text-zinc-950 tabular-nums">{counts[v]}</span> {LABEL[v]}
              </li>
            ))}
          </ul>
        )}
        <svg
          className={cx("ml-auto size-4 flex-none text-zinc-400 transition-transform", open && "rotate-180")}
          viewBox="0 0 16 16"
          fill="none"
          aria-hidden="true"
        >
          <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </button>
      {open && (
        <div className="grid animate-fade-in gap-8 px-5 pb-6 sm:px-6">
          <ClassBar tracks={tracks} expected={expected} />
          <StudentGrid subs={subs} activity={activity} />
        </div>
      )}
    </Card>
  );
}
