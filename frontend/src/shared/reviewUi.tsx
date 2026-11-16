import type { LectureReviewTask } from "./types";
import { Code } from "./ui";
import { cx } from "./cx";
import { issueName, percent, plural } from "./review";

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
