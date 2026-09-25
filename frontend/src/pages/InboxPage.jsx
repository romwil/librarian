import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { humanError } from "../copy.js";
import {
  INBOX_LIST_PARAMS,
  inboxCardCopy,
  inboxHeadline,
} from "../lib/notificationInbox.js";

/**
 * Household inbox — calm stack of notices (Projectionist peer, Librarian voice).
 */
export default function InboxPage() {
  const [loading, setLoading] = useState(true);
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [error, setError] = useState("");

  const reload = useCallback(() => {
    setLoading(true);
    setError("");
    const params = new URLSearchParams();
    if (INBOX_LIST_PARAMS.unread_only) params.set("unread_only", "1");
    params.set("limit", String(INBOX_LIST_PARAMS.limit));
    api
      .notifications(params)
      .then((data) => {
        setItems(data.items || []);
        setUnread(Number(data.unread_count) || 0);
        setLoading(false);
      })
      .catch((err) => {
        setItems([]);
        setUnread(0);
        setError(humanError(err));
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  async function handleDismiss(id) {
    setItems((prev) => prev.filter((row) => row.id !== id));
    setUnread((n) => Math.max(0, n - 1));
    try {
      await api.markNotificationsSeen({ ids: [id] });
    } catch {
      reload();
    }
  }

  async function handleDismissAll() {
    setItems([]);
    setUnread(0);
    try {
      await api.markNotificationsSeen({ all_unread: true });
    } catch {
      reload();
    }
  }

  const headline = inboxHeadline(items);

  return (
    <div className="admin-room inbox-page" data-testid="inbox-page">
      <header className="inbox-page-head">
        <p className="kicker">Inbox</p>
        <h1>{headline}</h1>
        <p className="lede">
          Notices from the house — arrivals, Needs you, quiet hours, and whispers. Adjust what lands here under
          Notifications.
        </p>
        <div className="inbox-page-actions">
          <Link className="cta outline compact" to="/notifications">
            Notification preferences
          </Link>
          {items.length ? (
            <button type="button" className="cta ghost compact" onClick={handleDismissAll}>
              Clear all
            </button>
          ) : null}
        </div>
      </header>

      {error ? <p className="alert">{error}</p> : null}
      {loading ? (
        <p className="muted" aria-busy="true">
          Checking the desk…
        </p>
      ) : null}
      {!loading && !items.length && !error ? (
        <div className="inbox-empty" data-testid="inbox-empty">
          <p className="lede">The desk is clear.</p>
          <p className="muted">When something arrives or needs you, it will wait here calmly.</p>
        </div>
      ) : null}

      <ul className="inbox-list" aria-label="Unread notices">
        {items.map((item) => {
          const copy = inboxCardCopy(item);
          return (
            <li key={item.id} className="inbox-card" data-testid="inbox-card">
              <p className="inbox-card-eyebrow">{copy.eyebrow}</p>
              {copy.href ? (
                <Link className="inbox-card-lead" to={copy.href}>
                  {copy.lead}
                </Link>
              ) : (
                <p className="inbox-card-lead">{copy.lead}</p>
              )}
              {copy.note ? <p className="inbox-card-note">{copy.note}</p> : null}
              <button
                type="button"
                className="cta ghost compact"
                onClick={() => handleDismiss(item.id)}
                aria-label={`Dismiss ${copy.lead}`}
              >
                Dismiss
              </button>
            </li>
          );
        })}
      </ul>
      {unread > 0 && !loading ? (
        <p className="sr-only" aria-live="polite">
          {unread} unread
        </p>
      ) : null}
    </div>
  );
}
