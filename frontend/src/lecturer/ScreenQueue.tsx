import { useEffect, useRef, useState } from "react";
import type { DragEvent, KeyboardEvent } from "react";
import type { ScreenQueueEntry } from "../shared/types";
import { Card } from "../shared/ui";
import { cx } from "../shared/cx";

export interface QueueEntryText {
  title: string;
  meta: string;
}

export interface ScreenQueuePanelProps {
  entries: ScreenQueueEntry[];
  // Time's up: the projector and students' screens are showing the queue,
  // one entry at a time (the projector steps through it). Before that, the
  // queue is only being lined up.
  live: boolean;
  // How an entry reads on the dashboard (names or class numbers, the issue's headline).
  describe: (entry: ScreenQueueEntry) => QueueEntryText;
  // A change is on its way to the server: hold further clicks until it lands.
  busy: boolean;
  error: string | null;
  onMove: (entry: ScreenQueueEntry, index: number) => void;
  onRemove: (entry: ScreenQueueEntry) => void;
}

// Everything the lecturer lined up to show the class, laid out like a
// presentation's slide strip: drag or Alt+arrow to reorder, x to drop. What's
// on screen is only *controlled* from the projector (2026-11-18) -- here it's
// just marked, so the lecturer can see where the room is.
export function ScreenQueuePanel({
  entries,
  live,
  describe,
  busy,
  error,
  onMove,
  onRemove,
}: ScreenQueuePanelProps) {
  const currentIndex = entries.findIndex((e) => e.current);
  const [dragId, setDragId] = useState<number | null>(null);
  const [dropIndex, setDropIndex] = useState<number | null>(null);
  const tileRefs = useRef(new Map<number, HTMLDivElement>());

  // Keep the tile that's on screen in view as the lecturer steps along.
  const currentId = live && currentIndex >= 0 ? entries[currentIndex].id : null;
  useEffect(() => {
    if (currentId == null) return;
    tileRefs.current.get(currentId)?.scrollIntoView({ block: "nearest", inline: "nearest", behavior: "smooth" });
  }, [currentId]);

  function endDrag() {
    setDragId(null);
    setDropIndex(null);
  }

  function drop(index: number) {
    const entry = entries.find((e) => e.id === dragId);
    const from = entries.findIndex((e) => e.id === dragId);
    endDrag();
    if (entry && from !== index) onMove(entry, index);
  }

  return (
    <Card flush>
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 px-5 pt-4 sm:px-6">
        <div className="flex min-w-0 items-baseline gap-3">
          <h2 className="text-[15px] font-bold tracking-tight text-zinc-950">Screen queue</h2>
          <p className="truncate text-[12px] text-zinc-500">
            {live ? "Step through it on the projector · drag to reorder" : "Shown one at a time on the projector when the task ends · drag to reorder"}
          </p>
        </div>
        <a
          href="present.html"
          target="_blank"
          rel="noopener"
          className="rounded-sm text-[12px] font-medium text-zinc-500 underline decoration-zinc-300 underline-offset-4 transition-colors hover:text-zinc-900 hover:decoration-zinc-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
        >
          Open projector ↗
        </a>
      </div>
      {error && <p className="px-5 pt-2 text-[13px] text-red-600 sm:px-6">{error}</p>}
      <div className="flex items-stretch gap-4 px-5 pt-3 pb-4 sm:px-6">
        <ol className="-mx-1 flex min-w-0 flex-1 gap-2 overflow-x-auto px-1 py-1" aria-label="Queued for the screen">
          {entries.map((entry, i) => {
            const text = describe(entry);
            const onScreen = live && entry.current;
            const dragging = dragId === entry.id;
            const dropTarget = dragId != null && dropIndex === i && !dragging;
            return (
              <li key={entry.id} className="flex-none">
                <div
                  ref={(el) => {
                    if (el) tileRefs.current.set(entry.id, el);
                    else tileRefs.current.delete(entry.id);
                  }}
                  draggable={!busy}
                  onDragStart={(e: DragEvent<HTMLDivElement>) => {
                    e.dataTransfer.effectAllowed = "move";
                    setDragId(entry.id);
                  }}
                  onDragOver={(e: DragEvent<HTMLDivElement>) => {
                    if (dragId == null) return;
                    e.preventDefault();
                    if (dropIndex !== i) setDropIndex(i);
                  }}
                  onDrop={(e: DragEvent<HTMLDivElement>) => {
                    e.preventDefault();
                    drop(i);
                  }}
                  onDragEnd={endDrag}
                  className={cx(
                    "group relative flex h-full w-52 flex-col rounded-lg border bg-white transition-[border-color,background-color,box-shadow,opacity]",
                    onScreen
                      ? "border-brand-500 bg-brand-50/70 shadow-[0_0_0_1px_var(--color-brand-500)]"
                      : "border-zinc-200 hover:border-zinc-300",
                    dragging && "opacity-40",
                    dropTarget && "border-dashed border-brand-400 bg-brand-50/40",
                    !busy && "cursor-grab active:cursor-grabbing",
                  )}
                >
                  <div
                    tabIndex={0}
                    onKeyDown={(e: KeyboardEvent<HTMLDivElement>) => {
                      if (busy || !e.altKey) return;
                      if (e.key === "ArrowLeft" && i > 0) {
                        e.preventDefault();
                        onMove(entry, i - 1);
                      } else if (e.key === "ArrowRight" && i < entries.length - 1) {
                        e.preventDefault();
                        onMove(entry, i + 1);
                      }
                    }}
                    aria-current={onScreen ? "true" : undefined}
                    aria-keyshortcuts="Alt+ArrowLeft Alt+ArrowRight"
                    aria-label={`${i + 1}. ${text.title}. ${text.meta}${onScreen ? ". On screen" : ""}. Alt+arrow keys to reorder`}
                    title="Drag or Alt+←/→ to reorder"
                    className="flex flex-1 flex-col rounded-lg p-3 pr-8 text-left focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
                  >
                    <span className="flex items-center gap-2 text-[11px]">
                      <span className={cx("font-mono tabular-nums", onScreen ? "font-semibold text-brand-600" : "text-zinc-400")}>
                        {String(i + 1).padStart(2, "0")}
                      </span>
                      {onScreen ? (
                        <span className="inline-flex items-center gap-1 font-medium text-brand-700">
                          <span className="size-1.5 animate-pulse-dot rounded-[2px] bg-brand-500" aria-hidden="true" />
                          On screen
                        </span>
                      ) : (
                        <span className="font-medium text-zinc-500">{entry.kind === "issue" ? "Discussion point" : "Attempt"}</span>
                      )}
                    </span>
                    <span className="mt-1.5 line-clamp-2 text-[13px] leading-snug font-medium text-zinc-950" title={text.title}>
                      {text.title}
                    </span>
                    <span className="mt-auto truncate pt-1.5 text-[11px] text-zinc-500" title={text.meta}>
                      {text.meta}
                    </span>
                  </div>
                  <button
                    type="button"
                    aria-label={`Remove ${text.title} from queue`}
                    title="Remove from queue"
                    onClick={() => onRemove(entry)}
                    disabled={busy}
                    className={cx(
                      "absolute top-2 right-2 inline-flex size-6 items-center justify-center rounded-md text-zinc-400 transition",
                      "opacity-0 group-hover:opacity-100 focus-visible:opacity-100",
                      "hover:bg-red-50 hover:text-red-600",
                      "focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-brand-500",
                      "disabled:cursor-not-allowed disabled:opacity-0",
                    )}
                  >
                    <svg className="size-3" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" aria-hidden="true">
                      <path d="M3 3l6 6M9 3l-6 6" />
                    </svg>
                  </button>
                </div>
              </li>
            );
          })}
        </ol>
      </div>
    </Card>
  );
}
