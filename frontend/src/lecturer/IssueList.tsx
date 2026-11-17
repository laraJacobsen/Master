import type { ClusterRow, SubmissionRow } from "../shared/types";
import { ExampleBlock } from "./ExampleBlock";
import { groupByShape, groupKey } from "./codeGroups";
import { CATEGORY_FILL, CATEGORY_LABEL, CATEGORY_PILL, categoryOf } from "../shared/categories";
import { Card } from "../shared/ui";
import { cx } from "../shared/cx";
import { issueKey } from "./issues";

// The headline: the AI's short title, else the note itself, else why there's none.
function headline(c: ClusterRow): string {
  if (c.title) return c.title;
  if (c.discussion_point) return c.discussion_point;
  return c.count < 2 ? "Only one student so far" : "No discussion point for this issue";
}

// What the lecturer could do about it.
function actionText(c: ClusterRow): string | null {
  if (c.action) return c.action;
  if (!c.discussion_point && c.count < 2) return "Show it to the students if it's worth going over anyway.";
  return null;
}

// "Runtime error" alone hides which one -- the pill names it.
function pillText(c: ClusterRow): string {
  const label = CATEGORY_LABEL[categoryOf(c.exec_verdict)];
  return c.error_type && c.error_type !== "none" ? `${label} · ${c.error_type}` : label;
}

export interface IssueListProps {
  issues: ClusterRow[];
  openKeys: Set<string>;
  onToggleOpen: (c: ClusterRow) => void;
  // The submissions behind an issue that are loaded so far.
  subsFor: (c: ClusterRow) => SubmissionRow[];
  loadError: boolean;
  raisingKey: string | null;
  // Null when there's no single live question to raise issues on.
  onToggleRaised: ((c: ClusterRow) => void) | null;
  // While the task runs, raising only queues: the backend holds raised
  // examples back from students and the projector until time is up.
  taskRunning: boolean;
}

// The discussion points, biggest first (raised ones on top). Each row is the
// overall error it falls under, the AI's headline and what to do about it;
// the arrow opens the specifics: the AI's factual note and the actual code.
export function IssueList({
  issues,
  openKeys,
  onToggleOpen,
  subsFor,
  loadError,
  raisingKey,
  onToggleRaised,
  taskRunning,
}: IssueListProps) {
  // Passing is in the verdict breakdown -- nothing to discuss.
  const points = issues.filter((c) => c.exec_verdict !== "pass");
  const raised = points.filter((c) => c.raised).length;
  return (
    <Card flush>
      <div className="px-5 pt-5 pb-4 sm:px-6 sm:pt-6">
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
          <div>
            <h2 className="text-lg font-semibold tracking-tight text-zinc-950">Discussion points</h2>
            <p className="mt-0.5 text-[13px] text-zinc-500">Patterns worth pausing on with the room</p>
          </div>
          {raised > 0 && (
            <span className="rounded-md bg-zinc-900 px-2 py-1 text-xs font-medium text-white">
              {taskRunning ? `${raised} queued · shown when time's up` : `${raised} on screen`}
            </span>
          )}
        </div>
        {raised === 0 && taskRunning && onToggleRaised && (
          <p className="mt-2 text-[12px] text-zinc-400">
            Queue points to put their example on screen once the task ends.
          </p>
        )}
      </div>
      {points.length === 0 ? (
        <div className="mx-5 mb-6 rounded-lg border border-dashed border-zinc-300 px-5 py-8 text-center text-sm text-zinc-400 sm:mx-6">
          Discussion points show up here as students submit.
        </div>
      ) : (
        <ul className="divide-y divide-zinc-100 border-t border-zinc-100">
          {points.map((c) => (
            <IssueRow
              key={issueKey(c)}
              issue={c}
              open={openKeys.has(issueKey(c))}
              onToggleOpen={() => onToggleOpen(c)}
              subs={subsFor(c)}
              loadError={loadError}
              raising={raisingKey === issueKey(c)}
              raiseBusy={raisingKey !== null}
              onToggleRaised={onToggleRaised ? () => onToggleRaised(c) : null}
              taskRunning={taskRunning}
            />
          ))}
        </ul>
      )}
    </Card>
  );
}

export interface IssueRowProps {
  issue: ClusterRow;
  open: boolean;
  onToggleOpen: () => void;
  subs: SubmissionRow[];
  loadError: boolean;
  raising: boolean;
  raiseBusy: boolean;
  onToggleRaised: (() => void) | null;
  taskRunning: boolean;
}

function IssueRow({
  issue: c,
  open,
  onToggleOpen,
  subs,
  loadError,
  raising,
  raiseBusy,
  onToggleRaised,
  taskRunning,
}: IssueRowProps) {
  const category = categoryOf(c.exec_verdict);
  const action = actionText(c);
  // The note is already the headline when the AI headline isn't there.
  const note = c.title ? c.discussion_point : null;
  return (
    <li>
      <button
        type="button"
        aria-expanded={open}
        onClick={onToggleOpen}
        className="group flex w-full items-stretch gap-4 px-5 py-4 text-left transition-colors hover:bg-zinc-50 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brand-500 sm:px-6"
      >
        <span className={cx("w-1 flex-none rounded-full", CATEGORY_FILL[category])} aria-hidden="true" />
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
            <span className={cx("rounded-md px-1.5 py-0.5 text-[11px] font-semibold whitespace-nowrap", CATEGORY_PILL[category])}>
              {pillText(c)}
            </span>
            <span
              className={cx(
                "text-[15px] leading-snug font-semibold",
                c.title || c.discussion_point ? "text-zinc-950" : "text-zinc-400",
                !open && !c.title && "line-clamp-2",
              )}
            >
              {headline(c)}
            </span>
            {c.raised && (
              <span className="rounded-md bg-zinc-900 px-1.5 py-0.5 text-[11px] font-semibold text-white">
                {taskRunning ? "Queued" : "On screen"}
              </span>
            )}
          </span>
          {action && <span className="mt-1 block text-[13px] leading-snug text-zinc-500">{action}</span>}
        </span>
        <span className="flex flex-none items-center gap-3">
          <span className="text-xs whitespace-nowrap text-zinc-400">
            <span className="font-mono text-zinc-600 tabular-nums">{c.count}</span> student{c.count === 1 ? "" : "s"}
          </span>
          <svg
            className={cx(
              "size-4 text-zinc-400 transition-[transform,color] group-hover:text-zinc-800",
              open && "rotate-90 text-zinc-800",
            )}
            viewBox="0 0 16 16"
            fill="none"
            aria-hidden="true"
          >
            <path d="M6 4l4 4-4 4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span className="sr-only">{open ? "Hide specifics" : "Show specifics"}</span>
        </span>
      </button>

      {open && (
        <div className="grid animate-fade-in gap-4 px-5 pb-6 sm:pr-6 sm:pl-11">
          {(note || onToggleRaised) && (
            <div className="flex flex-wrap items-start gap-x-6 gap-y-3">
              {note && <p className="min-w-0 flex-1 basis-56 text-[13px] leading-relaxed text-zinc-700">{note}</p>}
              {onToggleRaised && (
                <button
                  type="button"
                  aria-pressed={c.raised}
                  disabled={raiseBusy}
                  onClick={onToggleRaised}
                  title={
                    taskRunning
                      ? c.raised
                        ? "Take this out of the queue"
                        : "Queue this example: it goes on the projector and students' screens when the task ends"
                      : c.raised
                        ? "Stop showing this on the projector and students' screens"
                        : "Show this example on the projector and students' screens now"
                  }
                  className={cx(
                    "ml-auto inline-flex h-8 flex-none items-center gap-1.5 rounded-lg border px-3 text-[13px] font-medium whitespace-nowrap transition-colors",
                    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500 disabled:cursor-not-allowed",
                    raising && "cursor-wait",
                    c.raised
                      ? "border-brand-500 bg-brand-500 text-white hover:bg-brand-600"
                      : "border-zinc-200 bg-white text-zinc-700 hover:border-zinc-300 hover:bg-zinc-100 disabled:text-zinc-400",
                  )}
                >
                  {raising ? (
                    c.raised ? "Removing..." : taskRunning ? "Queueing..." : "Sharing..."
                  ) : c.raised ? (
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
              )}
            </div>
          )}
          <IssueCode subs={subs} loadError={loadError} />
        </div>
      )}
    </li>
  );
}

export interface IssueCodeProps {
  subs: SubmissionRow[];
  loadError: boolean;
  className?: string;
}

function IssueCode({ subs, loadError, className }: IssueCodeProps) {
  return (
    <div className={cx("grid animate-fade-in gap-5 text-[13px]", className)}>
      {subs.length > 0 ? (
        groupByShape(subs).map((group) => <ExampleBlock key={groupKey(group[0])} subs={group} />)
      ) : loadError ? (
        <span className="text-red-600">Could not load these submissions.</span>
      ) : (
        <span className="text-zinc-500">Loading...</span>
      )}
    </div>
  );
}
