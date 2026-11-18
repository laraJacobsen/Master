import { useEffect, useState } from "react";
import { cx } from "./cx";

// Small confirmations in the bottom-right corner ("Join link copied"). Any
// code can call toast(); the one <Toaster /> that bootstrap.tsx mounts on
// every page shows them. Plain window events rather than a context, so it
// works from event handlers and non-React modules alike.

export type ToastTone = "success" | "info" | "danger";

interface ToastItem {
  id: number;
  message: string;
  tone: ToastTone;
}

const TOAST_EVENT = "app-toast";
const TOAST_MS = 3200;
let nextId = 1;

export function toast(message: string, tone: ToastTone = "success"): void {
  window.dispatchEvent(new CustomEvent<ToastItem>(TOAST_EVENT, { detail: { id: nextId++, message, tone } }));
}

const DOT: Record<ToastTone, string> = {
  success: "bg-emerald-400",
  info: "bg-brand-300",
  danger: "bg-red-400",
};

export function Toaster() {
  const [items, setItems] = useState<ToastItem[]>([]);

  useEffect(() => {
    const onToast = (e: Event) => {
      const item = (e as CustomEvent<ToastItem>).detail;
      setItems((prev) => [...prev.slice(-2), item]); // at most three on screen
      window.setTimeout(() => setItems((prev) => prev.filter((t) => t.id !== item.id)), TOAST_MS);
    };
    window.addEventListener(TOAST_EVENT, onToast);
    return () => window.removeEventListener(TOAST_EVENT, onToast);
  }, []);

  return (
    <div
      role="status"
      aria-live="polite"
      className="pointer-events-none fixed right-5 bottom-5 z-[110] flex w-[min(22rem,calc(100vw-2.5rem))] flex-col items-end gap-2"
    >
      {items.map((t) => (
        <div
          key={t.id}
          className="pointer-events-auto flex animate-slide-in-right items-center gap-3 rounded-lg bg-zinc-900 px-4 py-3 text-[13px] font-medium text-white shadow-xl shadow-zinc-950/20"
        >
          <span className={cx("size-1.5 flex-none rounded-[2px]", DOT[t.tone])} aria-hidden="true" />
          <span className="min-w-0">{t.message}</span>
          <button
            type="button"
            onClick={() => setItems((prev) => prev.filter((x) => x.id !== t.id))}
            className="-mr-1.5 ml-auto rounded-md px-1.5 text-white/50 transition-colors hover:text-white focus-visible:outline-2 focus-visible:outline-white"
            aria-label="Dismiss"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}

/** Copy text to the clipboard and confirm it with a toast. */
export async function copyWithToast(text: string, what: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text);
    toast(`${what} copied`);
  } catch {
    toast(`Couldn't copy the ${what.toLowerCase()}. Select it and copy it by hand.`, "danger");
  }
}
