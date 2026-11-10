import { useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import type { ReactNode } from "react";

export interface DrawerProps {
  open: boolean;
  onClose: () => void;
  title: ReactNode;
  /** Small line under the title. */
  meta?: ReactNode;
  /** Sits under the header, above the scrolling body (e.g. tabs). */
  toolbar?: ReactNode;
  children: ReactNode;
}

// A panel that slides in from the right, for detail that can get long (a
// student's full code) without pushing the page around. The page behind stays
// visible; Escape, the close button or a click on the backdrop closes it.
export function Drawer({ open, onClose, title, meta, toolbar, children }: DrawerProps) {
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

  // Portalled to <body>: a sticky ancestor would otherwise trap it under the nav bar.
  return createPortal(
    <div className="fixed inset-0 z-[90] flex justify-end">
      <div className="absolute inset-0 animate-fade-in bg-zinc-950/15" onClick={onClose} aria-hidden="true" />
      <aside
        role="dialog"
        aria-modal="true"
        className="relative flex h-full w-full max-w-3xl animate-slide-in-right flex-col border-l border-zinc-200 bg-white shadow-2xl shadow-zinc-950/10"
      >
        <div className="flex items-start gap-4 border-b border-zinc-200 px-6 pt-5 pb-4 sm:px-8">
          <div className="min-w-0 flex-1">
            <h2 className="truncate text-xl font-bold tracking-tight text-zinc-950">{title}</h2>
            {meta && <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-zinc-500">{meta}</div>}
          </div>
          <button
            ref={closeRef}
            type="button"
            aria-label="Close"
            onClick={onClose}
            className="grid size-9 flex-none place-items-center rounded-lg text-zinc-500 transition-colors hover:bg-zinc-100 hover:text-zinc-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-zinc-900"
          >
            <svg className="size-4" viewBox="0 0 16 16" fill="none" aria-hidden="true">
              <path d="M4 4l8 8m0-8l-8 8" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
          </button>
        </div>
        {toolbar && <div className="border-b border-zinc-200 px-6 py-3 sm:px-8">{toolbar}</div>}
        <div className="min-h-0 flex-1 overflow-y-auto px-6 py-6 sm:px-8">{children}</div>
      </aside>
    </div>,
    document.body,
  );
}
