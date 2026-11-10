import { useState } from "react";
import type { QuestionRow } from "../shared/types";
import { Menu } from "../shared/Menu";
import type { MenuEntry } from "../shared/Menu";
import { Button, Eyebrow } from "../shared/ui";
import { cx } from "../shared/cx";

function formatMMSS(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds));
  const m = Math.floor(s / 60);
  const rem = s % 60;
  return `${m}:${rem.toString().padStart(2, "0")}`;
}

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

// The top of the live dashboard: what the task is, the clock, and the one
// next step. Everything else (join code, projector, setup, ending the lecture
// early) lives in the "more" menu. The task text itself is one click away --
// it can be long, and the lecturer wrote it.
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
  const fraction =
    question && secondsRemaining != null && question.duration_seconds > 0
      ? secondsRemaining / question.duration_seconds
      : 0;
  const example = question?.test_cases[0] ?? null;

  const menuItems: MenuEntry[] = [
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
      <div className="flex flex-wrap items-end justify-between gap-x-12 gap-y-6">
        <div className="min-w-0 flex-1 basis-96">
          <div className="flex items-center gap-3 text-[13px] font-medium">
            {running ? (
              <span className="inline-flex items-center gap-1.5 text-emerald-700">
                <span className="size-1.5 animate-pulse-dot rounded-[2px] bg-emerald-500" aria-hidden="true" />
                Live
              </span>
            ) : (
              <span className="text-zinc-500">{timeUp ? "Closed" : "Not running"}</span>
            )}
            {question && (
              <>
                <span className="text-zinc-300" aria-hidden="true">
                  /
                </span>
                <span className="text-zinc-500 capitalize">{question.language}</span>
              </>
            )}
            {lastTask && (
              <>
                <span className="text-zinc-300" aria-hidden="true">
                  /
                </span>
                <span className="text-zinc-500">Last task</span>
              </>
            )}
          </div>
          <h1 className="mt-3 text-4xl font-bold tracking-tight text-balance text-zinc-950 lg:text-5xl">{title}</h1>
          {question && (
            <button
              type="button"
              aria-expanded={showTask}
              onClick={() => setShowTask((v) => !v)}
              className="mt-3 inline-flex items-center gap-1.5 rounded-md py-0.5 text-[13px] font-medium text-zinc-500 transition-colors hover:text-zinc-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900"
            >
              <svg
                className={cx("size-3 transition-transform", showTask && "rotate-90")}
                viewBox="0 0 12 12"
                fill="none"
                aria-hidden="true"
              >
                <path d="M4.5 3l3 3-3 3" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              {showTask ? "Hide task" : "Show task"}
            </button>
          )}
        </div>

        <div className="flex items-end gap-8">
          <div className="text-right">
            <Eyebrow className={timeUp ? "text-red-600" : undefined}>{timeUp ? "Time's up" : "Time left"}</Eyebrow>
            <div
              className={cx(
                "mt-1 font-mono text-5xl leading-none font-semibold tracking-tight tabular-nums",
                timeUp ? "text-red-600" : "text-zinc-950",
              )}
              role="timer"
            >
              {secondsRemaining != null ? formatMMSS(secondsRemaining) : "--:--"}
            </div>
          </div>
          <div className="flex items-center gap-2">
            {running && (
              <Button variant="secondary" size="lg" onClick={onEndTaskNow} disabled={advancing}>
                End task now
              </Button>
            )}
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
      </div>

      {showTask && question && (
        <div className="mt-6 grid animate-fade-in gap-8 rounded-xl border border-zinc-200 bg-white p-6 lg:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
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

      {/* The time left as a line that drains across the page. */}
      <div className="mt-8 h-0.5 w-full bg-zinc-200" aria-hidden="true">
        <div
          className={cx(
            "h-full transition-[width] duration-1000 ease-linear",
            fraction <= 0.15 ? "bg-red-500" : "bg-zinc-900",
          )}
          style={{ width: `${Math.min(1, Math.max(0, fraction)) * 100}%` }}
        />
      </div>
      {(timeUp || advanceMessage) && (
        <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-[13px]">
          {timeUp && (
            <p className="flex items-center gap-2 text-zinc-600">
              <span className="size-1.5 animate-pulse-dot rounded-[2px] bg-amber-500" aria-hidden="true" />
              Students are waiting. Pick what to show them, then {lastTask ? "end the lecture" : "start the next task"}.
            </p>
          )}
          {advanceMessage && <p className="font-medium text-red-600">{advanceMessage}</p>}
        </div>
      )}
    </header>
  );
}
