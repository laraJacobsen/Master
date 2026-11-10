import type { ClusterRow, SubmissionRow } from "../shared/types";
import { ExampleBlock } from "./ExampleBlock";
import { groupByShape, groupKey } from "./codeGroups";
import { cx } from "../shared/cx";
import { issueKey, issueTag } from "./issues";

type IssueKind = "pass" | "wrong" | "error" | "rejected";

// Colour family for an issue's marker and bar -- same palette as the class bar.
function issueKind(c: ClusterRow): IssueKind {
  if (c.exec_verdict === "pass") return "pass";
  if (c.exec_verdict === "rejected") return "rejected";
  if (c.exec_verdict === "wrong_answer") return "wrong";
  return "error";
}

const KIND_FILL: Record<IssueKind, string> = {
  pass: "bg-emerald-600",
  wrong: "bg-amber-400",
  error: "bg-red-600",
  rejected: "bg-zinc-400",
};

function issueText(c: ClusterRow): string {
  if (c.discussion_point) return c.discussion_point;
  return c.count < 2
    ? "Only one student so far. Show it to the students if it's worth going over anyway."
    : "No discussion point for this issue.";
}

export interface IssueListProps {
  issues: ClusterRow[];
  // What an issue's bar is a share of: everyone who's submitted so far.
  classSize: number;
  openKeys: Set<string>;
  onToggleOpen: (c: ClusterRow) => void;
  // The submissions behind an issue that are loaded so far.
  subsFor: (c: ClusterRow) => SubmissionRow[];
  loadError: boolean;
  raisingKey: string | null;
  // Null when there's no single live question to raise issues on.
  onToggleRaised: ((c: ClusterRow) => void) | null;
}

// The issues the class is running into, biggest first, passing last. Each
// row is the count (with a bar for its share of the class), what went wrong
// and the discussion point; clicking it opens the actual code behind it.
export function IssueList({
  issues,
  classSize,
  openKeys,
  onToggleOpen,
  subsFor,
  loadError,
  raisingKey,
  onToggleRaised,
}: IssueListProps) {
  const problems = issues.filter((c) => c.exec_verdict !== "pass");
  const passing = issues.filter((c) => c.exec_verdict === "pass");

  if (issues.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-zinc-300 px-6 py-12 text-center text-sm text-zinc-400">
        Issues show up here as students submit.
      </div>
    );
  }

  return (
    <div>
      <ul className="border-t border-zinc-200">
        {problems.map((c) => (
          <IssueRow
            key={issueKey(c)}
            issue={c}
            classSize={classSize}
            open={openKeys.has(issueKey(c))}
            onToggleOpen={() => onToggleOpen(c)}
            subs={subsFor(c)}
            loadError={loadError}
            raising={raisingKey === issueKey(c)}
            raiseBusy={raisingKey !== null}
            onToggleRaised={onToggleRaised ? () => onToggleRaised(c) : null}
          />
        ))}
      </ul>
      {/* Passing is context ("how many got there"), not an issue to discuss. */}
      {passing.map((c) => {
        const open = openKeys.has(issueKey(c));
        return (
          <div key={issueKey(c)} className="mt-4">
            <button
              type="button"
              aria-expanded={open}
              onClick={() => onToggleOpen(c)}
              className="inline-flex items-center gap-2 rounded-md py-1 text-[13px] text-zinc-500 transition-colors hover:text-zinc-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900"
            >
              <span className="grid size-4 place-items-center rounded-[4px] bg-emerald-600 text-white" aria-hidden="true">
                <svg className="size-2.5" viewBox="0 0 10 10" fill="none">
                  <path d="M2 5.2l2 2L8 3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
              </span>
              <span>
                <span className="font-mono font-semibold text-zinc-900">{c.count}</span> passed every test
              </span>
              <span className="text-zinc-400">· {open ? "hide code" : "view code"}</span>
            </button>
            {open && (
              <IssueCode subs={subsFor(c)} loadError={loadError} className="mt-3" />
            )}
          </div>
        );
      })}
    </div>
  );
}

export interface IssueRowProps {
  issue: ClusterRow;
  classSize: number;
  open: boolean;
  onToggleOpen: () => void;
  subs: SubmissionRow[];
  loadError: boolean;
  raising: boolean;
  raiseBusy: boolean;
  onToggleRaised: (() => void) | null;
}

function IssueRow({
  issue: c,
  classSize,
  open,
  onToggleOpen,
  subs,
  loadError,
  raising,
  raiseBusy,
  onToggleRaised,
}: IssueRowProps) {
  const kind = issueKind(c);
  const share = Math.min(1, c.count / classSize);
  return (
    <li className={cx("border-b border-zinc-200 transition-colors", c.raised && "bg-zinc-50")}>
      <div className="flex flex-col gap-3 py-5 pr-1 sm:flex-row sm:items-start sm:gap-5">
        <button
          type="button"
          aria-expanded={open}
          onClick={onToggleOpen}
          className="group flex w-full min-w-0 flex-1 items-start gap-4 rounded-lg text-left focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-zinc-900 sm:gap-7"
        >
          <span className="w-14 flex-none pl-1 sm:w-16" title={`${c.count} of ${classSize} students who submitted`}>
            <span className="block font-mono text-4xl leading-none font-semibold tracking-tight text-zinc-950 tabular-nums">
              {c.count}
            </span>
            <span className="mt-2.5 block h-1 overflow-hidden rounded-sm bg-zinc-200" aria-hidden="true">
              <span className={cx("block h-full min-w-1 rounded-sm", KIND_FILL[kind])} style={{ width: `${share * 100}%` }} />
            </span>
          </span>
          <span className="min-w-0 flex-1">
            <span className="flex flex-wrap items-center gap-2 text-[13px] font-semibold text-zinc-500">
              <span className={cx("size-2 rounded-[2px]", KIND_FILL[kind])} aria-hidden="true" />
              {issueTag(c)}
              {c.raised && (
                <span className="rounded-md bg-zinc-900 px-1.5 py-0.5 text-[11px] font-medium text-white">On students' screens</span>
              )}
            </span>
            {/* Two lines until opened -- the full text is one click away. */}
            <span
              className={cx(
                "mt-1.5 block text-base leading-snug",
                c.discussion_point ? "text-zinc-900" : "text-zinc-400",
                !open && "line-clamp-2",
              )}
            >
              {issueText(c)}
            </span>
          </span>
          <svg
            className={cx(
              "mt-2 size-4 flex-none text-zinc-300 transition-[transform,color] group-hover:text-zinc-700",
              open && "rotate-180 text-zinc-700",
            )}
            viewBox="0 0 16 16"
            fill="none"
            aria-hidden="true"
          >
            <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
        {onToggleRaised && (
          <button
            type="button"
            aria-pressed={c.raised}
            disabled={raiseBusy}
            onClick={onToggleRaised}
            title={c.raised ? "Stop showing this on students' screens" : "Put this on students' screens when time is up"}
            className={cx(
              "ml-20 inline-flex h-8 flex-none items-center gap-1.5 self-start rounded-lg border px-3 sm:ml-0 text-[13px] font-medium whitespace-nowrap transition-colors",
              "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900 disabled:cursor-not-allowed",
              raising && "cursor-wait",
              c.raised
                ? "border-zinc-900 bg-zinc-900 text-white hover:bg-zinc-700"
                : "border-zinc-200 bg-white text-zinc-700 hover:border-zinc-300 hover:bg-zinc-100 disabled:text-zinc-400",
            )}
          >
            {raising ? (
              c.raised ? "Removing..." : "Sharing..."
            ) : c.raised ? (
              <>
                <svg className="size-3" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                  <path d="M2.5 6.2l2.3 2.3L9.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                Showing
              </>
            ) : (
              "Show to students"
            )}
          </button>
        )}
      </div>
      {open && <IssueCode subs={subs} loadError={loadError} className="pb-6 sm:pl-[6.5rem]" />}
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
