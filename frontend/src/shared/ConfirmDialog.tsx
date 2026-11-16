import { useEffect, useRef } from "react";
import { Button } from "./ui";

export interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  // Start focus on Cancel instead, for actions bad enough that a stray
  // Enter shouldn't trigger them (e.g. ending the whole lecture).
  focusCancel?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

// A styled stand-in for window.confirm() -- the native browser dialog can't
// be themed and reads as jarring next to the rest of the app. Escape and a
// backdrop click both cancel; the confirm button gets initial focus since
// it's almost always what the user came here to click (keyboard: Enter
// confirms, matching a native dialog's default button) -- unless
// `focusCancel` is set.
export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Delete",
  cancelLabel = "Cancel",
  focusCancel = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const confirmRef = useRef<HTMLButtonElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (!open) return;
    (focusCancel ? cancelRef : confirmRef).current?.focus();
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onCancel();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open, onCancel, focusCancel]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[100] flex animate-fade-in items-center justify-center bg-zinc-950/40 p-4 backdrop-blur-[2px]"
      onClick={onCancel}
    >
      <div
        className="w-full max-w-sm animate-fade-in-up rounded-xl border border-zinc-200 bg-white p-6 shadow-2xl shadow-zinc-950/10"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-message"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="confirm-dialog-title" className="text-lg font-bold tracking-tight text-zinc-950">
          {title}
        </h2>
        <p id="confirm-dialog-message" className="mt-2 text-sm text-zinc-500">
          {message}
        </p>
        <div className="mt-6 flex justify-end gap-2">
          <Button ref={cancelRef} variant="secondary" onClick={onCancel}>
            {cancelLabel}
          </Button>
          <Button ref={confirmRef} variant="danger" onClick={onConfirm}>
            {confirmLabel}
          </Button>
        </div>
      </div>
    </div>
  );
}
