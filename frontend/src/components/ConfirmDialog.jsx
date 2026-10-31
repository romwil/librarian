import { useId, useRef } from "react";
import useModal from "../hooks/useModal.js";
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

  useModal({
    open,
    onEscape: onCancel,
    panelRef,
    initialFocusRef: cancelRef,
    returnFocusRef,
  });

  if (!open) return null;

  return (
    <div className="whats-new-backdrop" data-testid={testId}>
      <button type="button" className="modal-scrim" aria-label="Close overlay" tabIndex={-1} onClick={() => onCancel?.()} />
      <div
        ref={panelRef}
        className="whats-new-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={bodyId}
      >
        <div className="whats-new-header">
          <h2 id={titleId} tabIndex={-1}>
            {title}
          </h2>
        </div>
        <div className="whats-new-body" id={bodyId} role="region" aria-label={title}>
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
