import { useRef } from "react";
import { Link } from "react-router-dom";
import useModal from "../hooks/useModal.js";
import ReleaseNotesPanel from "./ReleaseNotesPanel.jsx";

export default function WhatsNewModal({ open, version, release, onDismiss, onReadFull }) {
  const panelRef = useRef(null);
  const titleRef = useRef(null);
  const shown = Boolean(open && version);

  useModal({
    open: shown,
    onEscape: onDismiss,
    panelRef,
    initialFocusRef: titleRef,
  });

  if (!shown) return null;

  return (
    <div className="whats-new-backdrop" data-testid="whats-new-modal">
      <button type="button" className="modal-scrim" aria-label="Close overlay" tabIndex={-1} onClick={onDismiss} />
      <div
        ref={panelRef}
        className="whats-new-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="whats-new-title"
      >
        <div className="whats-new-header">
          <h2 id="whats-new-title" ref={titleRef} tabIndex={-1}>
            What’s new in {version}
          </h2>
          <button
            type="button"
            className="cta ghost whats-new-close"
            onClick={onDismiss}
            aria-label="Close"
            data-testid="whats-new-close"
          >
            ✕
          </button>
        </div>

        <div className="whats-new-body" role="region" aria-label="Release notes">
          {release ? (
            <ReleaseNotesPanel releases={[release]} preferHighlights testId="whats-new-notes" />
          ) : (
            <p className="muted" data-testid="whats-new-fallback">
              Librarian {version} is ready. Open Settings → About for the full release history.
            </p>
          )}
        </div>

        <div className="whats-new-actions">
          <button type="button" className="cta" data-testid="whats-new-got-it" onClick={onDismiss}>
            Got it
          </button>
          <Link
            to="/settings#about"
            className="cta ghost"
            data-testid="whats-new-read-full"
            onClick={onReadFull}
          >
            Read full notes
          </Link>
        </div>
      </div>
    </div>
  );
}
