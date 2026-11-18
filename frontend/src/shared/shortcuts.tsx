import { useEffect, useRef } from "react";
import { cx } from "./cx";
import { ROUTES } from "./routes";

/** Whether a key press belongs to a text field or the code editor, not to a page shortcut. */
export function isTypingTarget(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  return !!el?.closest?.("input, textarea, select, [contenteditable='true'], .monaco-editor");
}

export interface Shortcut {
  /** KeyboardEvent.key, e.g. "n" or "?". Letters match either case. */
  key: string;
  /** What it does, shown in the shortcuts dialog. */
  label: string;
  run: () => void;
}

/**
 * Single-key page shortcuts. Ignored while typing, with Ctrl/Cmd/Alt held,
 * or when something else already handled the key.
 */
export function useShortcuts(shortcuts: Shortcut[], enabled = true): void {
  const ref = useRef(shortcuts);
  ref.current = shortcuts;
  useEffect(() => {
    if (!enabled) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey || e.defaultPrevented || e.repeat || isTypingTarget(e.target)) return;
      const hit = ref.current.find((s) => s.key.toLowerCase() === e.key.toLowerCase());
      if (!hit) return;
      e.preventDefault();
      hit.run();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [enabled]);
}

export interface ShortcutRow {
  keys: string[];
  label: string;
}

export interface ShortcutsDialogProps {
  open: boolean;
  onClose: () => void;
  title?: string;
  rows: ShortcutRow[];
}

export function Kbd({ children, className }: { children: string; className?: string }) {
  return (
    <kbd
      className={cx(
        "inline-grid h-6 min-w-6 place-items-center rounded-md border border-zinc-200 bg-zinc-50 px-1.5 font-mono text-xs font-medium text-zinc-700 shadow-[0_1px_0_var(--color-zinc-200)]",
        className,
      )}
    >
      {children}
    </kbd>
  );
}

/** The "?" overlay: every shortcut on this page. */
export function ShortcutsDialog({ open, onClose, title = "Keyboard shortcuts", rows }: ShortcutsDialogProps) {
  const closeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return;
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-[100] flex animate-fade-in items-center justify-center bg-zinc-950/40 p-4 backdrop-blur-[2px]"
      onPointerDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="shortcuts-title"
        className="w-full max-w-md animate-fade-in-up rounded-xl border border-zinc-200 bg-white p-6 shadow-2xl shadow-zinc-950/10"
      >
        <div className="flex items-center justify-between gap-4">
          <h2 id="shortcuts-title" className="text-lg font-bold tracking-tight text-zinc-950">
            {title}
          </h2>
          <button
            ref={closeRef}
            type="button"
            onClick={onClose}
            className="rounded-md px-2 py-1 text-xs font-medium text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-500"
          >
            Close <span className="ml-1 font-mono text-zinc-400">Esc</span>
          </button>
        </div>
        <dl className="mt-5 divide-y divide-zinc-100">
          {rows.map((r) => (
            <div key={r.label} className="flex items-center justify-between gap-6 py-2.5">
              <dt className="text-sm text-zinc-700">{r.label}</dt>
              <dd className="flex flex-none gap-1">
                {r.keys.map((k) => (
                  <Kbd key={k}>{k}</Kbd>
                ))}
              </dd>
            </div>
          ))}
        </dl>
        <p className="mt-5 text-[13px] text-zinc-500">
          All shortcuts are listed on the{" "}
          <a href={ROUTES.help} className="font-medium text-brand-600 underline-offset-4 hover:underline">
            help page
          </a>
          .
        </p>
      </div>
    </div>
  );
}
