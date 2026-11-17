import { useState } from "react";
import type { StudentActivity, SubmissionRow } from "../shared/types";
import type { StudentTrack } from "./studentTracks";
import { StudentGrid } from "./StudentGrid";
import type { ShowCodeControl } from "./StudentGrid";
import { readShowNames, saveShowNames } from "./studentNames";
import { CATEGORY_FILL, CATEGORY_LABEL, CATEGORY_ORDER, categoryOf } from "../shared/categories";
import type { Category } from "../shared/categories";
import { Card } from "../shared/ui";
import { cx } from "../shared/cx";

type Row = Category | "not_submitted";

export interface VerdictBreakdownProps {
  tracks: StudentTrack[];
  subs: SubmissionRow[];
  // Null once the task isn't running.
  activity: StudentActivity[] | null;
  // "Show to students": the counts (never names) go on the students' waiting
  // screens and the projector -- queued while the task runs, like examples.
  resultsShown: boolean;
  taskRunning: boolean;
  showBusy: boolean;
  // Null hides the button.
  onToggleShown: (() => void) | null;
  // "Show on screen" for one student's attempt, in their code drawer.
  showCode?: ShowCodeControl;
}

// Each student's best result so far, a row per outcome category (the bar
// itself is up in the purple band). Every row opens to the students in it (collapsed by
// default -- names can end up on the projector); a student opens their code.
export function VerdictBreakdown({
  tracks,
  subs,
  activity,
  resultsShown,
  taskRunning,
  showBusy,
  onToggleShown,
  showCode,
}: VerdictBreakdownProps) {
  const [openRows, setOpenRows] = useState<Set<Row>>(new Set());
  const [showNames, setShowNames] = useState(readShowNames);

  const members = new Map<Row, Set<string>>();
  for (const t of tracks) {
    const row: Row = t.best ? categoryOf(t.best.exec_verdict) : "not_submitted";
    members.set(row, (members.get(row) ?? new Set()).add(t.name));
  }
  const count = (r: Row) => members.get(r)?.size ?? 0;
  const categories = CATEGORY_ORDER.filter((c) => count(c) > 0);
  const total = categories.reduce((n, c) => n + count(c), 0);
  const rows: Row[] = [...categories, ...(count("not_submitted") > 0 ? ["not_submitted" as const] : [])];

  function toggleRow(r: Row) {
    setOpenRows((prev) => {
      const next = new Set(prev);
      if (next.has(r)) next.delete(r);
      else next.add(r);
      return next;
    });
  }

  function toggleNames() {
    setShowNames((prev) => {
      saveShowNames(!prev);
      return !prev;
    });
  }

  return (
    <Card className="flex flex-col">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-zinc-950">Students by outcome</h2>
          <p className="mt-0.5 text-[13px] text-zinc-500">Open an outcome to see the students in it</p>
        </div>
        <div className="flex flex-none items-center gap-2">
          {openRows.size > 0 && (
            <button
              type="button"
              aria-pressed={showNames}
              onClick={toggleNames}
              className="rounded-md px-2 py-1 text-xs font-medium text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
            >
              {showNames ? "Hide names" : "Show names"}
            </button>
          )}
          <span className="rounded-md bg-zinc-100 px-2 py-1 font-mono text-xs text-zinc-600 tabular-nums">
            {total} result{total === 1 ? "" : "s"}
          </span>
        </div>
      </div>

      {total === 0 && rows.length === 0 && (
        <div className="mt-5 rounded-lg border border-dashed border-zinc-300 px-5 py-8 text-center text-sm text-zinc-400">
          Waiting for the first submission
        </div>
      )}

      {rows.length > 0 && (
        <ul className="mt-4 divide-y divide-zinc-100">
          {rows.map((r) => {
            const n = count(r);
            const open = openRows.has(r);
            const label = r === "not_submitted" ? "Not submitted yet" : CATEGORY_LABEL[r];
            return (
              <li key={r}>
                <button
                  type="button"
                  aria-expanded={open}
                  onClick={() => toggleRow(r)}
                  className="group -mx-2 grid w-[calc(100%+1rem)] grid-cols-[auto_1fr_auto_3rem_auto] items-center gap-3 rounded-md px-2 py-2.5 text-left text-sm transition-colors hover:bg-zinc-50 focus-visible:outline-2 focus-visible:outline-offset-0 focus-visible:outline-brand-500"
                >
                  <span
                    className={cx(
                      "size-2 rounded-[2px]",
                      r === "not_submitted" ? "border border-zinc-300 bg-white" : CATEGORY_FILL[r],
                    )}
                    aria-hidden="true"
                  />
                  <span className={r === "not_submitted" ? "text-zinc-500" : "text-zinc-800"}>{label}</span>
                  <span className="font-mono font-semibold text-zinc-950 tabular-nums">{n}</span>
                  <span className="text-right font-mono text-xs text-zinc-400 tabular-nums">
                    {r === "not_submitted" ? "" : `${Math.round((n / total) * 100)}%`}
                  </span>
                  <svg
                    className={cx(
                      "size-3.5 text-zinc-300 transition-[transform,color] group-hover:text-zinc-700",
                      open && "rotate-90 text-zinc-700",
                    )}
                    viewBox="0 0 16 16"
                    fill="none"
                    aria-hidden="true"
                  >
                    <path d="M6 4l4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                  </svg>
                  <span className="sr-only">{open ? `Hide ${label} students` : `Show ${label} students`}</span>
                </button>
                {open && (
                  <div className="animate-fade-in pt-1 pb-3 pl-5">
                    <StudentGrid
                      subs={subs}
                      activity={activity}
                      only={members.get(r)}
                      showNames={showNames}
                      showCode={showCode}
                    />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      {onToggleShown && (
        <div className="mt-4 flex flex-wrap items-center gap-x-6 gap-y-3 border-t border-zinc-100 pt-4">
          <p className="min-w-0 flex-1 basis-48 text-[13px] text-zinc-500">
            {resultsShown
              ? taskRunning
                ? "Queued: students see the counts when time's up."
                : "Students and the projector see the counts, no names."
              : "Share the counts with the class. Names stay hidden."}
          </p>
          <button
            type="button"
            aria-pressed={resultsShown}
            disabled={showBusy}
            onClick={onToggleShown}
            title={
              taskRunning
                ? resultsShown
                  ? "Take the results out of the queue"
                  : "Queue the results: they go on the projector and students' screens when the task ends"
                : resultsShown
                  ? "Stop showing the results on the projector and students' screens"
                  : "Show the results on the projector and students' screens now"
            }
            className={cx(
              "ml-auto inline-flex h-8 flex-none items-center gap-1.5 rounded-lg border px-3 text-[13px] font-medium whitespace-nowrap transition-colors",
              "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500 disabled:cursor-wait",
              resultsShown
                ? "border-brand-500 bg-brand-500 text-white hover:bg-brand-600"
                : "border-zinc-200 bg-white text-zinc-700 hover:border-zinc-300 hover:bg-zinc-100 disabled:text-zinc-400",
            )}
          >
            {showBusy ? (
              resultsShown ? "Removing..." : taskRunning ? "Queueing..." : "Sharing..."
            ) : resultsShown ? (
              <>
                <svg className="size-3" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                  <path d="M2.5 6.2l2.3 2.3L9.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                {taskRunning ? "Queued" : "Showing"}
              </>
            ) : taskRunning ? (
              "Add to queue"
            ) : (
              "Show on screen"
            )}
          </button>
        </div>
      )}
    </Card>
  );
}
