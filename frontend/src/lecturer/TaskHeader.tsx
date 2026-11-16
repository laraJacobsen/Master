import { useState } from "react";
import type { ActivityStatus, QuestionRow } from "../shared/types";
import { Menu } from "../shared/Menu";
import type { MenuEntry } from "../shared/Menu";
import { Button, Card, Eyebrow, formatMMSS } from "../shared/ui";
import { ACTIVITY_LABEL, isSolved } from "./studentTracks";
import type { StudentTrack } from "./studentTracks";
import { ActivityDot } from "./ClassProgress";
import { cx } from "../shared/cx";

export interface TaskHeaderProps {
  title: string;
  // "Introduction to Programming · Task 3 of 4" -- each part optional.
  lectureLabel: string | null;
  taskNumber: number | null;
  taskCount: number | null;
  question: QuestionRow | null;
  secondsRemaining: number | null;
  joinCode: string | null;
  // No draft left to start after this one -- the main action ends the lecture.
  lastTask: boolean;
  advancing: boolean;
  advanceMessage: string | null;
  onNextTask: () => void;
  onEndTaskNow: () => void;
  // Opens the "end the whole lecture?" confirm.
  onEndLecture: () => void;
}

// The top of the live dashboard: lecture and task position, the task name, and
// on the other side Next task plus a "..." menu for everything
// else (task text, ending the task early, join code, projector, setup).
export function TaskHeader({
  title,
  lectureLabel,
  taskNumber,
  taskCount,
  question,
  secondsRemaining,
  joinCode,
  lastTask,
  advancing,
  advanceMessage,
  onNextTask,
  onEndTaskNow,
  onEndLecture,
}: TaskHeaderProps) {
  const [showTask, setShowTask] = useState(false);
  const running = secondsRemaining != null && secondsRemaining > 0;
  const example = question?.test_cases[0] ?? null;

  const taskItems: MenuEntry[] = [
    ...(question ? [{ label: showTask ? "Hide task text" : "Show task text", onSelect: () => setShowTask((v) => !v) }] : []),
    ...(running ? [{ label: "End task now", disabled: advancing, onSelect: onEndTaskNow }] : []),
  ];
  const menuItems: MenuEntry[] = [
    ...taskItems,
    ...(taskItems.length ? ["separator" as const] : []),
    { label: "Projector view ↗", href: "present.html", newTab: true },
    { label: "Question setup", href: "setup.html" },
    "separator",
    // Ends the whole lecture for everyone -- kept in here, not on the page,
    // so it isn't clicked by accident (and it still asks to confirm).
    { label: "End session...", tone: "danger", disabled: advancing, onSelect: onEndLecture },
  ];
  const eyebrow = [
    lectureLabel,
    taskNumber != null && (taskCount != null ? `Task ${taskNumber} of ${taskCount}` : `Task ${taskNumber}`),
  ].filter(Boolean);

  return (
    <header className="pt-8 sm:pt-10">
      <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
        <div className="min-w-0 flex-1 basis-80">
          {eyebrow.length > 0 && <Eyebrow>{eyebrow.join(" · ")}</Eyebrow>}
          <h1 className="mt-1.5 text-3xl font-bold tracking-tight text-balance text-zinc-950 lg:text-4xl">{title}</h1>
        </div>
        <div className="flex items-center gap-2">
          {!lastTask && (
            <Button size="lg" onClick={onNextTask} disabled={advancing}>
              Next task
              <span aria-hidden="true">&rarr;</span>
            </Button>
          )}
          <Menu
            label="More actions"
            items={menuItems}
            header={
              joinCode && (
                <>
                  <Eyebrow>Join code</Eyebrow>
                  <div className="mt-1 font-mono text-2xl font-bold tracking-[0.16em] text-zinc-950">{joinCode}</div>
                </>
              )
            }
          />
        </div>
      </div>
      {advanceMessage && <p className="mt-3 text-[13px] font-medium text-red-600">{advanceMessage}</p>}

      {showTask && question && (
        <div className="mt-6 grid animate-fade-in gap-8 rounded-xl bg-white p-6 shadow-card lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
          <div className="min-w-0">
            <Eyebrow>Task</Eyebrow>
            <p className="mt-2 max-h-72 overflow-y-auto pr-2 text-[15px] leading-relaxed whitespace-pre-wrap text-zinc-800">
              {question.prompt}
            </p>
            {question.output_file && (
              <p className="mt-3 text-[13px] text-zinc-500">
                Graded on the file <span className="font-mono text-zinc-900">{question.output_file}</span>, not printed
                output.
              </p>
            )}
          </div>
          {example && (
            <div className="grid min-w-0 content-start gap-4">
              <div>
                <Eyebrow>Example input</Eyebrow>
                <pre className="mt-2 max-h-40 overflow-auto rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 font-mono text-[13px] text-zinc-900">
                  {example.stdin.trimEnd() || "(none)"}
                </pre>
              </div>
              <div>
                <Eyebrow>{question.output_file ? `Expected ${question.output_file}` : "Expected output"}</Eyebrow>
                <pre className="mt-2 max-h-40 overflow-auto rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 font-mono text-[13px] text-zinc-900">
                  {example.expected_stdout.trimEnd()}
                </pre>
              </div>
            </div>
          )}
        </div>
      )}
    </header>
  );
}

export interface TaskStatusCardProps {
  question: QuestionRow | null;
  secondsRemaining: number | null;
  submitted: number;
  expected: number | null;
  tracks: StudentTrack[];
  // Activity only means something while students can still type.
  showActivity: boolean;
  lastTask: boolean;
}

// "18 / 42 submitted" with a submissions bar, and the time remaining with its
// own draining bar, split by a divider.
export function TaskStatusCard({
  question,
  secondsRemaining,
  submitted,
  expected,
  tracks,
  showActivity,
  lastTask,
}: TaskStatusCardProps) {
  const running = secondsRemaining != null && secondsRemaining > 0;
  const timeUp = secondsRemaining === 0;
  const timeFraction =
    question && secondsRemaining != null && question.duration_seconds > 0
      ? Math.min(1, Math.max(0, secondsRemaining / question.duration_seconds))
      : 0;
  const submittedFraction = expected ? Math.min(1, submitted / expected) : submitted > 0 ? 1 : 0;
  const notSubmitted = expected != null ? Math.max(0, expected - submitted) : null;
  const unsolved = tracks.filter((t) => !isSolved(t));
  const activityCounts = (["active", "idle", "away"] as ActivityStatus[]).map(
    (st) => [st, unsolved.filter((t) => (t.activity?.status ?? "away") === st).length] as const,
  );

  return (
    <Card className="mt-6">
      <div className="flex flex-wrap items-stretch justify-between gap-x-8 gap-y-5">
        <div className="min-w-0 flex-1 basis-72">
          <div className="flex items-center gap-2">
            {running ? (
              <span className="grid size-3.5 place-items-center rounded-full border border-emerald-500" aria-hidden="true">
                <span className="size-1.5 animate-pulse-dot rounded-full bg-emerald-500" />
              </span>
            ) : (
              <span className="size-2 rounded-full bg-zinc-300" aria-hidden="true" />
            )}
            <Eyebrow>{running ? "Live submissions" : timeUp ? "Submissions · closed" : "Submissions"}</Eyebrow>
          </div>
          <p className="mt-2 flex items-baseline gap-1.5">
            <span className="font-mono text-4xl leading-none font-semibold tracking-tight text-zinc-950 tabular-nums">
              {submitted}
            </span>
            {expected != null && submitted <= expected && (
              <span className="text-xl text-zinc-400 tabular-nums">/ {expected}</span>
            )}
            <span className="text-xl text-zinc-400">submitted</span>
            {expected != null && submitted > expected && (
              <span className="ml-1 text-sm text-zinc-500">· more than the {expected} expected</span>
            )}
          </p>
        </div>
        <div className="flex flex-col items-end justify-center border-zinc-200 sm:border-l sm:pl-8">
          <Eyebrow className={timeUp ? "text-red-600" : undefined}>{timeUp ? "Time's up" : "Time remaining"}</Eyebrow>
          <div
            role="timer"
            className={cx(
              "mt-1.5 font-mono text-3xl leading-none font-semibold tracking-tight tabular-nums",
              timeUp ? "text-red-600" : "text-zinc-950",
            )}
          >
            {secondsRemaining != null ? formatMMSS(secondsRemaining) : "--:--"}
          </div>
          <div className="mt-2.5 h-1 w-28 overflow-hidden rounded-full bg-zinc-100" aria-hidden="true">
            <div
              className={cx(
                "ml-auto h-full rounded-full transition-[width,background-color] duration-1000 ease-linear",
                timeFraction <= 0.15 ? "bg-red-500" : timeFraction <= 0.4 ? "bg-amber-500" : "bg-zinc-800",
              )}
              style={{ width: `${timeFraction * 100}%` }}
            />
          </div>
        </div>
      </div>

      <div
        className="mt-5 h-2 overflow-hidden rounded-full bg-zinc-100"
        role="progressbar"
        aria-label="Submitted"
        aria-valuemin={0}
        aria-valuemax={expected ?? submitted}
        aria-valuenow={submitted}
      >
        <div
          className="h-full rounded-full bg-brand-500 transition-[width] duration-700 ease-out"
          style={{ width: `${submittedFraction * 100}%` }}
        />
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-x-6 gap-y-2 text-[12px] text-zinc-500">
        {showActivity && unsolved.length > 0 ? (
          <ul
            className="flex gap-4"
            aria-label="Students who haven't solved it, by activity"
            title="Students who haven't solved it yet. Idle: no typing for a few minutes. Away: editor not open."
          >
            {activityCounts.map(([st, n]) => (
              <li key={st} className={cx("flex items-center gap-1.5", st === "idle" && n > 0 && "font-semibold text-zinc-900")}>
                <ActivityDot status={st} />
                <span className="font-mono tabular-nums">{n}</span> {ACTIVITY_LABEL[st]}
              </li>
            ))}
          </ul>
        ) : (
          <span>{question ? <span className="capitalize">{question.language}</span> : null}{lastTask && " · Last task"}</span>
        )}
        {notSubmitted != null && (
          <span>
            <span className="font-mono font-semibold text-zinc-900 tabular-nums">{notSubmitted}</span> not yet submitted
          </span>
        )}
      </div>
      {timeUp && (
        <p className="mt-3 flex items-center gap-2 text-[13px] text-zinc-600">
          <span className="size-1.5 animate-pulse-dot rounded-[2px] bg-amber-500" aria-hidden="true" />
          Students are waiting. The queued examples are on screen now. {lastTask ? "End the session from the ··· menu" : "Start the next task"} when you're done.
        </p>
      )}
    </Card>
  );
}
