import { useEffect, useState } from "react";
import { READER_WELCOME_GOT_IT, READER_WELCOME_LEDE, READER_WELCOME_TITLE } from "../copy.js";

const storageKey = (userId) => `librarian.reader-welcome.${userId}`;

export default function ReaderWelcomeGate({ user } = {}) {
  const [open, setOpen] = useState(false);
  const reader = user?.role === "reader";
  const userId = user?.id;

  useEffect(() => {
    if (!reader || !userId) {
      setOpen(false);
      return;
    }
    try {
      if (window.localStorage.getItem(storageKey(userId))) {
        setOpen(false);
        return;
      }
    } catch {
      /* private mode */
    }
    setOpen(true);
  }, [reader, userId]);

  if (!open) return null;

  function dismiss() {
    try {
      if (userId) window.localStorage.setItem(storageKey(userId), "1");
    } catch {
      /* ignore */
    }
    setOpen(false);
  }

  return (
    <div className="whats-new-backdrop" data-testid="reader-welcome" onClick={dismiss}>
      <div
        className="whats-new-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="reader-welcome-title"
        onClick={(event) => event.stopPropagation()}
      >
        <div className="whats-new-header">
          <h2 id="reader-welcome-title">{READER_WELCOME_TITLE}</h2>
        </div>
        <div className="whats-new-body">
          <p className="lede">{READER_WELCOME_LEDE}</p>
        </div>
        <div className="whats-new-actions">
          <button type="button" className="cta" onClick={dismiss}>
            {READER_WELCOME_GOT_IT}
          </button>
        </div>
      </div>
    </div>
  );
}
