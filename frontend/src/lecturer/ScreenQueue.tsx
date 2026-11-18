import type { ReactNode } from "react";
import type { ScreenQueueEntry } from "../shared/types";
import { Button, Card } from "../shared/ui";
import { cx } from "../shared/cx";

export interface QueueEntryText {
  title: string;
  meta: string;
}

export interface ScreenQueuePanelProps {
  entries: ScreenQueueEntry[];
  // Time's up: the projector and students' screens are showing the queue,
  // one entry at a time. Before that, the queue is only being lined up.
  live: boolean;
  // How an entry reads on the dashboard (names or class numbers, the issue's headline).
  describe: (entry: ScreenQueueEntry) => QueueEntryText;
  // A change is on its way to the server: hold further clicks until it lands.
  busy: boolean;
  error: string | null;
  onMove: (entry: ScreenQueueEntry, index: number) => void;
  onRemove: (entry: ScreenQueueEntry) => void;
  onShow: (entry: ScreenQueueEntry) => void;
  onStep: (step: number) => void;
}

// Everything the lecturer lined up to show the class, in order. While the
// task runs it's a list to sort out (reorder, drop); once time is up the
// class sees one entry at a time and this is where the lecturer moves along
// (the projector has the same Previous/Next).
export function ScreenQueuePanel({
  entries,
  live,
  describe,
  busy,
  error,
  onMove,
  onRemove,
  onShow,
  onStep,
}: ScreenQueuePanelProps) {
  const currentIndex = entries.findIndex((e) => e.current);
  return (
    <Card flush>
      <div className="flex flex-wrap items-start justify-between gap-x-6 gap-y-3 px-5 pt-5 pb-4 sm:px-6">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-zinc-950">Screen queue</h2>
          <p className="mt-0.5 text-[13px] text-zinc-500">
            {live
              ? "On the projector and students' screens, one at a time"
              : "Goes on the projector and students' screens one at a time when the task ends"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <a
            href="present.html"
            target="_blank"
            rel="noopener"
            className="mr-2 rounded-sm text-[13px] font-medium text-zinc-500 underline decoration-zinc-300 underline-offset-4 transition-colors hover:text-zinc-900 hover:decoration-zinc-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
          >
            Projector view ↗
          </a>
          {live && (
            <>
              <Button variant="secondary" size="sm" onClick={() => onStep(-1)} disabled={busy || currentIndex <= 0}>
                ← Previous
              </Button>
              <span className="min-w-14 text-center font-mono text-[13px] text-zinc-500 tabular-nums">
                {currentIndex + 1} / {entries.length}
              </span>
              <Button size="sm" onClick={() => onStep(1)} disabled={busy || currentIndex >= entries.length - 1}>
                Next →
              </Button>
            </>
          )}
        </div>
      </div>
      {error && <p className="px-5 pb-3 text-[13px] text-red-600 sm:px-6">{error}</p>}
      <ol className="divide-y divide-zinc-100 border-t border-zinc-100">
        {entries.map((entry, i) => {
          const text = describe(entry);
          const onScreen = live && entry.current;
          return (
            <li
              key={entry.id}
              className={cx(
                "grid grid-cols-[2rem_minmax(0,1fr)_auto] items-center gap-x-3 border-l-2 py-3 pr-5 pl-[calc(1.25rem-2px)] sm:pr-6 sm:pl-[calc(1.5rem-2px)]",
                onScreen ? "border-brand-500 bg-brand-50/60" : "border-transparent",
              )}
            >
              <span className={cx("font-mono text-sm tabular-nums", onScreen ? "font-semibold text-brand-600" : "text-zinc-400")}>
                {String(i + 1).padStart(2, "0")}
              </span>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-zinc-950" title={text.title}>
                  {text.title}
                </p>
                <p className="mt-0.5 truncate text-[12px] text-zinc-500">{text.meta}</p>
              </div>
              <div className="flex items-center gap-1.5">
                {live &&
                  (onScreen ? (
                    <span className="mr-1 inline-flex h-8 items-center gap-1.5 px-2 text-[13px] font-medium text-brand-700">
                      <span className="size-1.5 animate-pulse-dot rounded-[2px] bg-brand-500" aria-hidden="true" />
                      On screen
                    </span>
                  ) : (
                    <Button variant="secondary" size="sm" className="mr-1" onClick={() => onShow(entry)} disabled={busy}>
                      Show now
                    </Button>
                  ))}
                <IconButton label="Move up" onClick={() => onMove(entry, i - 1)} disabled={busy || i === 0}>
                  <path d="M6 9.5V2.5M3 5.5l3-3 3 3" />
                </IconButton>
                <IconButton label="Move down" onClick={() => onMove(entry, i + 1)} disabled={busy || i === entries.length - 1}>
                  <path d="M6 2.5v7M3 6.5l3 3 3-3" />
                </IconButton>
                <IconButton label="Remove from queue" onClick={() => onRemove(entry)} disabled={busy} danger>
                  <path d="M3 3l6 6M9 3l-6 6" />
                </IconButton>
              </div>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

export interface IconButtonProps {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
  // The icon's strokes, drawn in a 12x12 box.
  children: ReactNode;
}

function IconButton({ label, onClick, disabled, danger, children }: IconButtonProps) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
      className={cx(
        "inline-flex size-8 flex-none items-center justify-center rounded-lg border border-zinc-200 bg-white text-zinc-500 transition-colors",
        "hover:border-zinc-300 hover:bg-zinc-100 hover:text-zinc-900",
        danger && "hover:border-red-200 hover:bg-red-50 hover:text-red-600",
        "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500",
        "disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:border-zinc-200 disabled:hover:bg-white disabled:hover:text-zinc-500",
      )}
    >
      <svg className="size-3" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        {children}
      </svg>
    </button>
  );
}
