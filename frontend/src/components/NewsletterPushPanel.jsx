import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { humanError } from "../copy.js";
import {
  NEWSLETTER_SCOPES,
  newsletterConfirmMessage,
  newsletterResultMessage,
} from "../lib/notificationInbox.js";

/**
 * Owner early-push / self-test for personalized library editions.
 * Opt-in still required; never force-email.
 */
export default function NewsletterPushPanel({ mailConfigured = false } = {}) {
  const [scope, setScope] = useState("self");
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState("");

  async function handlePush() {
    const confirmed = window.confirm(newsletterConfirmMessage(scope));
    if (!confirmed) return;
    setBusy(true);
    setStatus("");
    try {
      const result = await api.pushNewsletter({ scope, force: true });
      setStatus(newsletterResultMessage(result));
    } catch (err) {
      setStatus(humanError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      className="settings-panel"
      data-testid="newsletter-push-panel"
      aria-labelledby="newsletter-push-heading"
    >
      <p className="kicker" id="newsletter-push-heading">
        Library letter
      </p>
      <h2>Send an edition early</h2>
      <p className="lede">
        Push the personalized letter now — recent arrivals shaped by Continue, Favorites, and Requests. Only members who
        opted in receive it; email leaves only when Mail is configured and they chose email.
      </p>
      <p className="muted">
        Members opt in under Notifications below
        {mailConfigured ? "" : (
          <>
            {" "}
            · Email stays off until <Link to="/settings#mail">Mail</Link> is configured (inbox still works)
          </>
        )}
        .
      </p>
      <label className="field">
        <span>Send to</span>
        <select
          value={scope}
          onChange={(event) => setScope(event.target.value)}
          aria-label="Newsletter send scope"
        >
          {NEWSLETTER_SCOPES.map((opt) => (
            <option key={opt.value} value={opt.value}>
              {opt.label}
            </option>
          ))}
        </select>
      </label>
      <div className="notifications-prefs-actions">
        <button type="button" className="cta" disabled={busy} onClick={handlePush}>
          {busy ? "Sending…" : "Send library letter now"}
        </button>
      </div>
      {status ? (
        <p className="muted" role="status">
          {status}
        </p>
      ) : null}
    </section>
  );
}
