import { useState } from "react";
import type { StudentActivity, SubmissionRow } from "../shared/types";
import type { StudentTrack } from "./studentTracks";
import { StudentGrid } from "./StudentGrid";
import { readShowNames, saveShowNames } from "./studentNames";
import { CATEGORY_FILL, CATEGORY_LABEL, CATEGORY_ORDER, categoryOf } from "./categories";
import type { Category } from "./categories";
import { Card } from "../shared/ui";
import { cx } from "../shared/cx";

type Row = Category | "not_submitted";

export interface VerdictBreakdownProps {
  tracks: StudentTrack[];
  subs: SubmissionRow[];
  // Null once the task isn't running.
  activity: StudentActivity[] | null;
}

// Each student's best result so far, by outcome category: a stacked bar and a
// row per category. Every row opens to the students in it (collapsed by
// default -- names can end up on the projector); a student opens their code.
export function VerdictBreakdown({ tracks, subs, activity }: VerdictBreakdownProps) {
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
          <h2 className="text-lg font-semibold tracking-tight text-zinc-950">Verdict breakdown</h2>
          <p className="mt-0.5 text-[13px] text-zinc-500">Automatic test results across submitted code</p>
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

      {total === 0 ? (
        <div className="mt-5 rounded-lg border border-dashed border-zinc-300 px-5 py-8 text-center text-sm text-zinc-400">
          Waiting for the first submission
        </div>
      ) : (
        <div
          className="mt-5 flex h-3 gap-0.5 overflow-hidden rounded-full"
          role="img"
          aria-label={categories.map((c) => `${count(c)} ${CATEGORY_LABEL[c]}`).join(", ")}
        >
          {categories.map((c) => (
            <span
              key={c}
              className={cx("min-w-1.5 basis-0 transition-[flex-grow] duration-500", CATEGORY_FILL[c])}
              style={{ flexGrow: count(c) }}
              title={`${count(c)} ${CATEGORY_LABEL[c]}`}
            />
          ))}
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
                    <StudentGrid subs={subs} activity={activity} only={members.get(r)} showNames={showNames} />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}
