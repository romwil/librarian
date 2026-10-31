import { useEffect, useId, useRef } from "react";
import { ThinkingButton } from "./Thinking.jsx";

/** Modal confirm. Escape cancels; focus starts on Cancel and returns to the opener on close. */
export default function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  onConfirm,
  onCancel,
  busy = false,
  confirmDisabled = false,
  confirmTestId = "confirm-dialog-confirm",
  returnFocusRef = null,
  testId = "confirm-dialog",
}) {
  const titleId = useId();
  const bodyId = useId();
  const panelRef = useRef(null);
  const cancelRef = useRef(null);
  const onCancelRef = useRef(onCancel);
  onCancelRef.current = onCancel;

  useEffect(() => {
    if (!open) return undefined;
    const opener = returnFocusRef?.current || null;
    cancelRef.current?.focus();
    function onKey(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        onCancelRef.current?.();
        return;
      }
      if (event.key !== "Tab" || !panelRef.current) return;
      const focusable = [...panelRef.current.querySelectorAll("button:not([disabled])")];
      if (!focusable.length) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      if (opener && typeof opener.focus === "function") opener.focus();
    };
  }, [open, returnFocusRef]);

  if (!open) return null;

  return (
    <div className="whats-new-backdrop" data-testid={testId} onClick={() => onCancel?.()}>
      <div
        ref={panelRef}
        className="whats-new-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={bodyId}
        onClick={(event) => event.stopPropagation()}
      >
        <div className="whats-new-header">
          <h2 id={titleId}>{title}</h2>
        </div>
        <div className="whats-new-body" id={bodyId}>
          {children}
        </div>
        <div className="whats-new-actions">
          <button ref={cancelRef} type="button" className="cta outline" onClick={() => onCancel?.()}>
            {cancelLabel}
          </button>
          {confirmLabel && onConfirm ? (
            <ThinkingButton
              type="button"
              className="cta"
              onClick={() => onConfirm()}
              busy={busy}
              disabled={confirmDisabled}
              data-testid={confirmTestId}
            >
              {confirmLabel}
            </ThinkingButton>
          ) : null}
        </div>
      </div>
    </div>
  );
}
