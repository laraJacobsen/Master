import { useState } from "react";
import type { ReactNode } from "react";
import type { ClusterRow, SubmissionRow } from "../shared/types";
import { ExampleBlock, SubmissionDetail } from "./ExampleBlock";
import { StudentTile } from "./StudentGrid";
import { LABEL, verdictOf } from "./studentTracks";
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
  // Null when there's no single live question to queue snippets on.
  snippetQueue: SnippetQueueControl | null;
  taskRunning: boolean;
  // A student's tile label: their name, or their class number when names are hidden.
  studentLabel: (name: string) => string;
  namesShown: boolean;
}

// "Add to queue" on one snippet of a discussion point: that exact code (no
// name) goes in the screen queue. The projector steps through the queue.
export interface SnippetQueueControl {
  // Which of this issue's submissions are queued.
  queuedIds: (c: ClusterRow) => Set<number>;
  busyId: number | null;
  onToggle: (c: ClusterRow, sub: SubmissionRow) => void;
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
  snippetQueue,
  taskRunning,
  studentLabel,
  namesShown,
}: IssueListProps) {
  // Passing is in the verdict breakdown -- nothing to discuss.
  const points = issues.filter((c) => c.exec_verdict !== "pass");
  const queued = snippetQueue ? points.reduce((n, c) => n + snippetQueue.queuedIds(c).size, 0) : 0;
  return (
    <Card flush>
      <div className="px-5 pt-5 pb-4 sm:px-6 sm:pt-6">
        <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
          <div>
            <h2 className="text-lg font-semibold tracking-tight text-zinc-950">Discussion points</h2>
            <p className="mt-0.5 text-[13px] text-zinc-500">Patterns worth pausing on with the room</p>
          </div>
          {queued > 0 && (
            <span className="rounded-md bg-zinc-900 px-2 py-1 text-xs font-medium text-white">
              {queued} snippet{queued === 1 ? "" : "s"} queued
            </span>
          )}
        </div>
        {queued === 0 && snippetQueue && (
          <p className="mt-2 text-[12px] text-zinc-400">
            Open a point and queue the exact snippet you want on the projector.
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
              snippetQueue={snippetQueue}
              taskRunning={taskRunning}
              studentLabel={studentLabel}
              namesShown={namesShown}
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
  snippetQueue: SnippetQueueControl | null;
  taskRunning: boolean;
  studentLabel: (name: string) => string;
  namesShown: boolean;
}

function IssueRow({
  issue: c,
  open,
  onToggleOpen,
  subs,
  loadError,
  snippetQueue,
  taskRunning,
  studentLabel,
  namesShown,
}: IssueRowProps) {
  const queuedIds = snippetQueue?.queuedIds(c) ?? new Set<number>();
  // The "Add to queue" for one snippet, next to its code.
  const queueAction = snippetQueue
    ? (sub: SubmissionRow) => (
        <QueueSnippetButton
          queued={queuedIds.has(sub.id)}
          busy={snippetQueue.busyId === sub.id}
          disabled={snippetQueue.busyId !== null}
          taskRunning={taskRunning}
          onClick={() => snippetQueue.onToggle(c, sub)}
        />
      )
    : undefined;
  // The one student whose code is shown instead of the grouped code.
  const [selectedId, setSelectedId] = useState<number | null>(null);
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
            {queuedIds.size > 0 && (
              <span className="rounded-md bg-zinc-900 px-1.5 py-0.5 text-[11px] font-semibold text-white">
                {queuedIds.size > 1 ? `${queuedIds.size} queued` : "Queued"}
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
          {note && <p className="text-[13px] leading-relaxed text-zinc-700">{note}</p>}
          <IssueStudents
            subs={subs}
            selectedId={selectedId}
            onSelect={(id) => setSelectedId((prev) => (prev === id ? null : id))}
            studentLabel={studentLabel}
            namesShown={namesShown}
          />
          <IssueCode
            subs={subs}
            loadError={loadError}
            selected={subs.find((s) => s.id === selectedId) ?? null}
            selectedLabel={(s) => studentLabel(s.student_name)}
            onClearSelected={() => setSelectedId(null)}
            action={queueAction}
          />
        </div>
      )}
    </li>
  );
}

// A student's latest attempt in this issue -- one tile per student, even if
// several of their attempts landed here.
function latestPerStudent(subs: SubmissionRow[]): SubmissionRow[] {
  const latest = new Map<string, SubmissionRow>();
  for (const sub of subs) {
    const prev = latest.get(sub.student_name);
    if (!prev || sub.id > prev.id) latest.set(sub.student_name, sub);
  }
  return [...latest.values()];
}

export interface IssueStudentsProps {
  subs: SubmissionRow[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  studentLabel: (name: string) => string;
  namesShown: boolean;
}

// The students who made this mistake, as the same tiles as "Students by
// outcome" (coloured by this attempt, not their best). A tile swaps the code
// below for that student's own; clicking it again goes back.
function IssueStudents({ subs, selectedId, onSelect, studentLabel, namesShown }: IssueStudentsProps) {
  const students = latestPerStudent(subs).sort((a, b) =>
    studentLabel(a.student_name).localeCompare(studentLabel(b.student_name), undefined, { numeric: true }),
  );
  if (students.length === 0) return null;
  return (
    <div>
      <p className="mb-2 text-xs text-zinc-500">
        Students with this issue · click one to see their code
      </p>
      <ul
        className={cx(
          "grid gap-1.5",
          namesShown
            ? "grid-cols-[repeat(auto-fill,minmax(7.5rem,1fr))]"
            : "grid-cols-[repeat(auto-fill,minmax(3.25rem,1fr))]",
        )}
      >
        {students.map((sub) => {
          const label = studentLabel(sub.student_name);
          return (
            <li key={sub.student_name}>
              <StudentTile
                label={label}
                mono={!namesShown}
                verdict={verdictOf(sub)}
                share={sub.tests_total ? sub.tests_passed / sub.tests_total : 0}
                pressed={selectedId === sub.id}
                onClick={() => onSelect(sub.id)}
                title={`${label}: ${LABEL[verdictOf(sub)]}, ${sub.tests_passed}/${sub.tests_total} tests, attempt ${sub.attempt_number}`}
              />
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export interface IssueCodeProps {
  subs: SubmissionRow[];
  loadError: boolean;
  // One student's attempt to show instead of the grouped code.
  selected: SubmissionRow | null;
  selectedLabel: (sub: SubmissionRow) => string;
  onClearSelected: () => void;
  // A control for one snippet (e.g. "Add to queue"), shown above its code.
  action?: (sub: SubmissionRow) => ReactNode;
  className?: string;
}

function IssueCode({ subs, loadError, selected, selectedLabel, onClearSelected, action, className }: IssueCodeProps) {
  if (selected) {
    return (
      <div key={selected.id} className={cx("grid animate-fade-in text-[13px]", className)}>
        <div className="mb-2 flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1 text-xs text-zinc-500">
          <span>
            <strong className="font-semibold text-zinc-900">{selectedLabel(selected)}</strong> · attempt{" "}
            {selected.attempt_number} ·{" "}
            <span className="font-mono">
              {selected.tests_passed}/{selected.tests_total}
            </span>{" "}
            tests
          </span>
          <span className="flex items-center gap-2">
            {action?.(selected)}
            <button
              type="button"
              onClick={onClearSelected}
              className="rounded-md px-2 py-1 font-medium text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
            >
              Back to all code
            </button>
          </span>
        </div>
        <SubmissionDetail sub={selected} />
      </div>
    );
  }
  return (
    <div className={cx("grid animate-fade-in gap-5 text-[13px]", className)}>
      {subs.length > 0 ? (
        groupByShape(subs).map((group) => <ExampleBlock key={groupKey(group[0])} subs={group} action={action} />)
      ) : loadError ? (
        <span className="text-red-600">Could not load these submissions.</span>
      ) : (
        <span className="text-zinc-500">Loading...</span>
      )}
    </div>
  );
}

export interface QueueSnippetButtonProps {
  queued: boolean;
  busy: boolean;
  disabled: boolean;
  taskRunning: boolean;
  onClick: () => void;
}

// Same look and states as the code drawer's "Add to queue" (StudentGrid.tsx).
function QueueSnippetButton({ queued, busy, disabled, taskRunning, onClick }: QueueSnippetButtonProps) {
  return (
    <button
      type="button"
      aria-pressed={queued}
      disabled={disabled}
      onClick={onClick}
      title={
        queued
          ? "Take this snippet out of the screen queue"
          : `Add this exact code to the screen queue, as the student wrote it and without their name. ${
              taskRunning ? "It goes up when the task ends; " : ""
            }the projector steps through the queue.`
      }
      className={cx(
        "inline-flex h-7 flex-none items-center gap-1.5 rounded-lg border px-2.5 text-[12px] font-medium whitespace-nowrap transition-colors",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500 disabled:cursor-not-allowed",
        busy && "cursor-wait",
        queued
          ? "border-brand-500 bg-brand-500 text-white hover:bg-brand-600"
          : "border-zinc-200 bg-white text-zinc-700 hover:border-zinc-300 hover:bg-zinc-100 disabled:text-zinc-400",
      )}
    >
      {busy ? (
        queued ? "Removing..." : "Queueing..."
      ) : queued ? (
        <>
          <svg className="size-3" viewBox="0 0 12 12" fill="none" aria-hidden="true">
            <path d="M2.5 6.2l2.3 2.3L9.5 3.5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          Queued
        </>
      ) : (
        "Add to queue"
      )}
    </button>
  );
}
