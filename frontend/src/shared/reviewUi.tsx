import { useState } from "react";
import type { LectureReviewTask } from "./types";
import { Code } from "./ui";
import { cx } from "./cx";
import { issueName, percent, plural } from "./review";
import type { Topic } from "./review";

// Small review components shared by the history page and the lecturer home.

export interface MeterProps {
  rate: number;
  size?: "sm" | "md";
  className?: string;
}

// One neutral hue on every bar -- a low share says "go back over this", not
// "failed", so no red/amber/green here.
export function Meter({ rate, size = "md", className }: MeterProps) {
  return (
    <span
      className={cx(
        "inline-block overflow-hidden rounded-sm bg-zinc-200 align-middle",
        size === "md" ? "h-1.5 w-28" : "h-1 w-full",
        className,
      )}
      role="img"
      aria-label={`${percent(rate)} solved`}
    >
      <span className="block h-full rounded-sm bg-brand-500" style={{ width: percent(rate) }} />
    </span>
  );
}

// What went wrong, as concretely as the data allows: for a wrong answer, the
// actual output most of them printed; otherwise the error kind and its line.
export interface IssueLineProps {
  task: LectureReviewTask;
  /** E.g. "line-clamp-2" where space is tight. */
  className?: string;
}

export function IssueLine({ task, className }: IssueLineProps) {
  const issue = task.top_issue;
  if (!issue) {
    return task.submitted === 0 ? <p className={cx("mt-2 text-[13px] text-zinc-500", className)}>No submissions</p> : null;
  }
  const ex = issue.example;
  if (ex?.test_name) {
    return (
      <p className={cx("mt-2 text-[13px] leading-relaxed text-zinc-700", className)}>
        <strong className="font-semibold text-zinc-900">{plural(ex.students, "student")}</strong> failed{" "}
        <Code>{ex.test_name}</Code>
        {ex.message ? (
          <>
            : <Code>{ex.message}</Code>
          </>
        ) : null}
      </p>
    );
  }
  if (ex) {
    return (
      <p className={cx("mt-2 text-[13px] leading-relaxed text-zinc-700", className)}>
        <strong className="font-semibold text-zinc-900">{plural(ex.students, "student")}</strong> printed{" "}
        <Code>{ex.stdout || "(nothing)"}</Code> for input <Code>{ex.stdin.trim() || "(empty)"}</Code>, expected{" "}
        <Code>{ex.expected_stdout.trim()}</Code>
      </p>
    );
  }
  return (
    <p className={cx("mt-2 text-[13px] leading-relaxed text-zinc-700", className)}>
      <strong className="font-semibold text-zinc-900">{plural(issue.students, "student")}</strong>:{" "}
      {issueName(issue.exec_verdict, issue.error_type)}
      {issue.discussion_point && <span className="text-zinc-500"> {issue.discussion_point}</span>}
    </p>
  );
}

export interface DeltaProps {
  /** Difference as a share (0.05 = 5 percentage points). */
  value: number;
  /** What it's compared with. */
  label?: string;
  className?: string;
}

/** "+5 pts since last month" (or another `label`) -- green up, red down, grey when flat. */
export function Delta({ value, label = "since last month", className }: DeltaProps) {
  const pts = Math.round(value * 100);
  const tone = pts > 0 ? "text-emerald-700" : pts < 0 ? "text-red-600" : "text-zinc-500";
  const sign = pts > 0 ? "+" : pts < 0 ? "\u2212" : "\u00b1";
  return (
    <div className={cx("mt-2 text-[11px] font-normal", tone, className)}>
      {sign}
      {Math.abs(pts)} pts {label}
    </div>
  );
}

export interface TopicItemProps {
  topic: Topic;
}

// One topic to revisit: its name and how it went. What students actually got
// wrong stays closed until the lecturer opens it.
export function TopicItem({ topic: t }: TopicItemProps) {
  const [open, setOpen] = useState(false);
  const panelId = `topic-panel-${t.title.replace(/[^a-zA-Z0-9]+/g, "-")}`;
  return (
    <li className="py-1 first:pt-0 last:pb-0">
      <button
        type="button"
        className={cx(
          "group -mx-3 grid w-[calc(100%+1.5rem)] gap-1.5 rounded-lg px-3 py-3 text-left transition-colors focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-brand-500",
          open ? "bg-brand-50/70" : "hover:bg-zinc-50",
        )}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="flex items-baseline justify-between gap-3">
          <span className="text-sm font-semibold text-zinc-900">{t.title}</span>
          <span className="flex items-center gap-2">
            <span className="font-mono text-sm font-semibold tabular-nums">{percent(t.rate)}</span>
            <svg
              className={cx("size-4 flex-none self-center text-zinc-400 transition-transform group-hover:text-zinc-700", open && "rotate-180")}
              viewBox="0 0 16 16"
              fill="none"
              aria-hidden="true"
            >
              <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
        </span>
        <Meter rate={t.rate} size="sm" />
        <span className="text-xs text-zinc-500">{plural(t.lectures, "lecture")}</span>
        <span className="sr-only">{open ? "Hide what went wrong" : "Show what went wrong"}</span>
      </button>
      {open && (
        <div id={panelId} className="animate-fade-in pb-3">
          <IssueLine task={t.worst} />
        </div>
      )}
    </li>
  );
}
