import { useEffect, useRef, useState } from "react";
import type { KeyboardEvent, ReactNode } from "react";
import { cx } from "./cx";

export interface MenuAction {
  label: ReactNode;
  /** Runs the action; the menu closes first. */
  onSelect?: () => void;
  /** Makes the item a link instead. */
  href?: string;
  newTab?: boolean;
  tone?: "default" | "danger";
  disabled?: boolean;
}

export type MenuEntry = MenuAction | "separator";

export interface MenuProps {
  /** Accessible name of the trigger button. */
  label: string;
  items: MenuEntry[];
  /** Non-interactive content at the top of the panel. */
  header?: ReactNode;
  className?: string;
}

// A small "more actions" menu: keeps rarely used actions one click away
// instead of on the page. Closes on Escape, an outside click, or a choice;
// arrow keys move between items.
export function Menu({ label, items, header, className }: MenuProps) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const panelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    panelRef.current?.querySelector<HTMLElement>("[role=menuitem]:not([aria-disabled=true])")?.focus();
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  function close() {
    setOpen(false);
    triggerRef.current?.focus();
  }

  function onPanelKey(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key === "Escape") {
      e.preventDefault();
      close();
      return;
    }
    if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
    e.preventDefault();
    const els = [...(panelRef.current?.querySelectorAll<HTMLElement>("[role=menuitem]:not([aria-disabled=true])") ?? [])];
    const at = els.indexOf(document.activeElement as HTMLElement);
    const next = e.key === "ArrowDown" ? (at + 1) % els.length : (at - 1 + els.length) % els.length;
    els[next]?.focus();
  }

  const itemClass = (tone: MenuAction["tone"], disabled?: boolean) =>
    cx(
      "flex w-full items-center gap-2 rounded-md px-3 py-2 text-left text-sm transition-colors outline-none",
      tone === "danger" ? "text-red-600 hover:bg-red-50 focus:bg-red-50" : "text-zinc-800 hover:bg-zinc-100 focus:bg-zinc-100",
      disabled && "pointer-events-none opacity-40",
    );

  return (
    <div ref={rootRef} className={cx("relative", className)}>
      <button
        ref={triggerRef}
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
        className={cx(
          "grid size-9 place-items-center rounded-lg border border-zinc-200 bg-white text-zinc-600 transition-colors",
          "hover:border-zinc-300 hover:bg-zinc-100 hover:text-zinc-900",
          "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900",
          open && "border-zinc-300 bg-zinc-100 text-zinc-900",
        )}
      >
        <svg className="size-4" viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
          <circle cx="3" cy="8" r="1.4" />
          <circle cx="8" cy="8" r="1.4" />
          <circle cx="13" cy="8" r="1.4" />
        </svg>
      </button>
      {open && (
        <div
          ref={panelRef}
          role="menu"
          aria-label={label}
          onKeyDown={onPanelKey}
          className="absolute top-full right-0 z-40 mt-2 w-64 origin-top-right animate-pop-in rounded-xl border border-zinc-200 bg-white p-1 shadow-xl shadow-zinc-950/5"
        >
          {header && <div className="border-b border-zinc-100 px-3 pt-2 pb-3">{header}</div>}
          <div className={header ? "pt-1" : undefined}>
            {items.map((item, i) =>
              item === "separator" ? (
                <div key={i} className="my-1 h-px bg-zinc-100" role="separator" />
              ) : item.href ? (
                <a
                  key={i}
                  role="menuitem"
                  href={item.href}
                  target={item.newTab ? "_blank" : undefined}
                  rel={item.newTab ? "noopener" : undefined}
                  aria-disabled={item.disabled || undefined}
                  className={itemClass(item.tone, item.disabled)}
                  onClick={() => setOpen(false)}
                >
                  {item.label}
                </a>
              ) : (
                <button
                  key={i}
                  type="button"
                  role="menuitem"
                  aria-disabled={item.disabled || undefined}
                  className={itemClass(item.tone, item.disabled)}
                  onClick={() => {
                    if (item.disabled) return;
                    setOpen(false);
                    item.onSelect?.();
                  }}
                >
                  {item.label}
                </button>
              ),
            )}
          </div>
        </div>
      )}
    </div>
  );
}
