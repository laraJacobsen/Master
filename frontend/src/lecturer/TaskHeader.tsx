import { useState } from "react";
import type { ActivityStatus, QuestionRow } from "../shared/types";
import { Menu } from "../shared/Menu";
import type { MenuEntry } from "../shared/Menu";
import { Button, Card, Eyebrow, StatusLine, formatMMSS } from "../shared/ui";
import { ACTIVITY_LABEL, isSolved } from "./studentTracks";
import type { StudentTrack } from "./studentTracks";
import { ActivityDot } from "./ClassProgress";
import { cx } from "../shared/cx";

export interface TaskHeaderProps {
  title: string;
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

// The top of the live dashboard: the task name, and on the other side the one
// next step plus a "..." menu for everything else (task text, ending the task
// early, join code, projector, setup, ending the lecture).
export function TaskHeader({
  title,
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
  const timeUp = secondsRemaining === 0;
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
    {
      label: lastTask ? "End lecture..." : "End lecture early...",
      tone: "danger",
      disabled: advancing,
      onSelect: onEndLecture,
    },
  ];

  return (
    <header className="pt-8 sm:pt-10">
      <div className="flex flex-wrap items-center justify-between gap-x-8 gap-y-4">
        <h1 className="min-w-0 flex-1 basis-80 text-3xl font-bold tracking-tight text-balance text-zinc-950 lg:text-4xl">
          {title}
        </h1>
        <div className="flex items-center gap-2">
          {lastTask ? (
            <Button variant={timeUp ? "primary" : "secondary"} size="lg" onClick={onEndLecture} disabled={advancing}>
              End lecture
            </Button>
          ) : (
            <Button variant={timeUp ? "primary" : "secondary"} size="lg" onClick={onNextTask} disabled={advancing}>
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

// "12/20 submitted" and the time remaining, with the time drawn as a draining bar.
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
  const fraction =
    question && secondsRemaining != null && question.duration_seconds > 0
      ? Math.min(1, Math.max(0, secondsRemaining / question.duration_seconds))
      : 0;
  const unsolved = tracks.filter((t) => !isSolved(t));
  const activityCounts = (["active", "idle", "away"] as ActivityStatus[]).map(
    (st) => [st, unsolved.filter((t) => (t.activity?.status ?? "away") === st).length] as const,
  );

  return (
    <Card className="mt-6">
      <div className="flex flex-wrap items-end justify-between gap-x-8 gap-y-4">
        <div>
          <Eyebrow>Submitted</Eyebrow>
          <p className="mt-1 flex items-baseline gap-2">
            <span className="font-mono text-4xl leading-none font-semibold tracking-tight text-zinc-950 tabular-nums">
              {submitted}
            </span>
            {expected != null && submitted <= expected && (
              <span className="font-mono text-xl text-zinc-400 tabular-nums">/ {expected}</span>
            )}
            <span className="ml-1 text-sm text-zinc-500">
              submitted
              {expected != null && submitted > expected && ` · more than the ${expected} expected`}
            </span>
          </p>
        </div>
        <div className="text-right">
          <Eyebrow className={timeUp ? "text-red-600" : undefined}>{timeUp ? "Time's up" : "Time remaining"}</Eyebrow>
          <div
            role="timer"
            className={cx(
              "mt-1 font-mono text-4xl leading-none font-semibold tracking-tight tabular-nums",
              timeUp ? "text-red-600" : "text-zinc-950",
            )}
          >
            {secondsRemaining != null ? formatMMSS(secondsRemaining) : "--:--"}
          </div>
        </div>
      </div>

      <div
        className="mt-5 h-3 overflow-hidden rounded-full bg-zinc-100"
        role="progressbar"
        aria-label="Time remaining"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(fraction * 100)}
      >
        <div
          className={cx(
            "h-full rounded-full transition-[width,background-color] duration-1000 ease-linear",
            fraction <= 0.15 ? "bg-red-500" : fraction <= 0.4 ? "bg-amber-400" : "bg-brand-500",
          )}
          style={{ width: `${fraction * 100}%` }}
        />
      </div>

      <div className="mt-3 flex flex-wrap items-center justify-between gap-x-6 gap-y-2 text-[13px]">
        <StatusLine
          state={running ? "live" : timeUp ? "closed" : "idle"}
          label={running ? "Live" : timeUp ? "Closed" : "Not running"}
          items={[question && <span className="capitalize">{question.language}</span>, lastTask && "Last task"]}
        />
        {showActivity && unsolved.length > 0 && (
          <ul
            className="flex gap-5 text-zinc-500"
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
        )}
      </div>
      {timeUp && (
        <p className="mt-3 flex items-center gap-2 text-[13px] text-zinc-600">
          <span className="size-1.5 animate-pulse-dot rounded-[2px] bg-amber-500" aria-hidden="true" />
          Students are waiting. Pick what to show them, then {lastTask ? "end the lecture" : "start the next task"}.
        </p>
      )}
    </Card>
  );
}
