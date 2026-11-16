import type { ClusterRow, SubmissionRow } from "../shared/types";
import { ExampleBlock } from "./ExampleBlock";
import { groupByShape, groupKey } from "./codeGroups";
import { Card } from "../shared/ui";
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

// The discussion points, grouped by the overall error they fall under (biggest
// group first). Each point is a headline and what to do about it; the arrow
// opens the specifics: the AI's factual note and the actual code behind it.
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

  // Grouped by category, keeping the server's order (raised, then biggest) within
  // a group; groups with a raised point come first, then the biggest.
  const groups = new Map<string, ClusterRow[]>();
  for (const c of problems) groups.set(issueTag(c), [...(groups.get(issueTag(c)) ?? []), c]);
  const ordered = [...groups.entries()].sort(([, a], [, b]) => {
    const raised = Number(b.some((c) => c.raised)) - Number(a.some((c) => c.raised));
    if (raised) return raised;
    return Math.max(...b.map((c) => c.count)) - Math.max(...a.map((c) => c.count));
  });

  if (issues.length === 0) {
    return (
      <div className="rounded-xl border border-dashed border-zinc-300 px-6 py-12 text-center text-sm text-zinc-400">
        Discussion points show up here as students submit.
      </div>
    );
  }

  return (
    <div className="grid gap-4">
      {ordered.map(([tag, points]) => (
        <Card key={tag} flush>
          <div className="flex items-center gap-2 border-b border-zinc-100 px-5 py-3 text-[13px] font-semibold text-zinc-600 sm:px-6">
            <span className={cx("size-2.5 rounded-[3px]", KIND_FILL[issueKind(points[0])])} aria-hidden="true" />
            {tag}
            {points.length > 1 && <span className="font-normal text-zinc-400">· {points.length} points</span>}
          </div>
          <ul className="divide-y divide-zinc-100">
            {points.map((c) => (
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
        </Card>
      ))}
      {problems.length === 0 && (
        <div className="rounded-xl border border-dashed border-zinc-300 px-6 py-8 text-center text-sm text-zinc-400">
          Nothing to discuss yet.
        </div>
      )}
      {/* Passing is context ("how many got there"), not an issue to discuss. */}
      {passing.map((c) => {
        const open = openKeys.has(issueKey(c));
        return (
          <div key={issueKey(c)}>
            <button
              type="button"
              aria-expanded={open}
              onClick={() => onToggleOpen(c)}
              className="inline-flex items-center gap-2 rounded-md py-1 text-[13px] text-zinc-500 transition-colors hover:text-zinc-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
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
            {open && <IssueCode subs={subsFor(c)} loadError={loadError} className="mt-3" />}
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
  const action = actionText(c);
  // The note is already the headline when the AI headline isn't there.
  const note = c.title ? c.discussion_point : null;
  return (
    <li className={cx("border-l-2 transition-colors", c.raised ? "border-l-zinc-900" : "border-l-transparent")}>
      <button
        type="button"
        aria-expanded={open}
        onClick={onToggleOpen}
        className="group flex w-full items-start gap-4 px-5 py-4 text-left transition-colors hover:bg-zinc-50 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brand-500 sm:gap-5 sm:px-6"
      >
        <span className="w-10 flex-none pt-0.5" title={`${c.count} of ${classSize} students who submitted`}>
          <span className="block font-mono text-2xl leading-none font-semibold tracking-tight text-zinc-950 tabular-nums">
            {c.count}
          </span>
          <span className="mt-2 block h-1 overflow-hidden rounded-sm bg-zinc-200" aria-hidden="true">
            <span className={cx("block h-full min-w-1 rounded-sm", KIND_FILL[kind])} style={{ width: `${share * 100}%` }} />
          </span>
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
            <span
              className={cx(
                "text-base leading-snug font-semibold",
                c.title || c.discussion_point ? "text-zinc-950" : "text-zinc-400",
                !open && !c.title && "line-clamp-2",
              )}
            >
              {headline(c)}
            </span>
            {c.raised && (
              <span className="rounded-md bg-zinc-900 px-1.5 py-0.5 text-[11px] font-semibold text-white">On screen</span>
            )}
          </span>
          {action && <span className="mt-1 block text-[14px] leading-snug text-zinc-600">{action}</span>}
        </span>
        <svg
          className={cx(
            "mt-1 size-4 flex-none text-zinc-300 transition-[transform,color] group-hover:text-zinc-700",
            open && "rotate-180 text-zinc-700",
          )}
          viewBox="0 0 16 16"
          fill="none"
          aria-hidden="true"
        >
          <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <span className="sr-only">{open ? "Hide specifics" : "Show specifics"}</span>
      </button>

      {open && (
        <div className="grid animate-fade-in gap-4 px-5 pb-6 sm:px-6 sm:pl-[5.25rem]">
          {(note || onToggleRaised) && (
            <div className="flex flex-wrap items-start gap-x-6 gap-y-3">
              {note && <p className="min-w-0 flex-1 basis-64 text-[13px] leading-relaxed text-zinc-700">{note}</p>}
              {onToggleRaised && (
                <button
                  type="button"
                  aria-pressed={c.raised}
                  disabled={raiseBusy}
                  onClick={onToggleRaised}
                  title={
                    c.raised
                      ? "Stop showing this on the full-screen projector view"
                      : "Put this on the full-screen projector view (and students' screens) when time is up"
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
                    c.raised ? "Removing..." : "Sharing..."
                  ) : c.raised ? (
                    <>
                      <svg className="size-3" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                        <path d="M2.5 6.2l2.3 2.3L9.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                      </svg>
                      Showing
                    </>
                  ) : (
                    "Show on full screen"
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
