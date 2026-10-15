import { useEffect, useRef } from "react";

interface ConfirmDialogProps {
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
    <div className="confirm-backdrop" onClick={onCancel}>
      <div
        className="confirm-dialog"
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-message"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 id="confirm-dialog-title">{title}</h2>
        <p id="confirm-dialog-message">{message}</p>
        <div className="confirm-dialog-actions">
          <button ref={cancelRef} className="secondary" onClick={onCancel}>
            {cancelLabel}
          </button>
          <button ref={confirmRef} className="danger" onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
