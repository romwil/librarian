import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { humanError } from "../copy.js";
import { normalizeChannels, normalizeTiming } from "../lib/notificationInbox.js";

const TIMING_OPTIONS = [
  { value: "realtime", label: "Realtime" },
  { value: "daily", label: "Daily digest" },
  { value: "weekly", label: "Weekly digest" },
];

/**
 * Per-kind notification preferences — Settings and /notifications.
 */
export default function NotificationsPrefsPanel({ showOwnerTest = false } = {}) {
  const [ready, setReady] = useState(false);
  const [email, setEmail] = useState("");
  const [catalog, setCatalog] = useState([]);
  const [kinds, setKinds] = useState({});
  const [channels, setChannels] = useState([]);
  const [mailConfigured, setMailConfigured] = useState(false);
  const [status, setStatus] = useState("");
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    api
      .notificationPrefs()
      .then((data) => {
        setEmail(data.notification_email || "");
        setCatalog(Array.isArray(data.catalog) ? data.catalog : []);
        setKinds(data.kinds || {});
        setChannels(Array.isArray(data.channels) ? data.channels : []);
        setMailConfigured(Boolean(data.mail_configured));
        setReady(true);
      })
      .catch((err) => {
        setStatus(humanError(err));
        setReady(true);
      });
  }, []);

  function patchKind(id, partial) {
    setKinds((prev) => {
      const current = prev[id] || { enabled: true, channels: ["inbox"], timing: "realtime" };
      return {
        ...prev,
        [id]: {
          ...current,
          ...partial,
          channels: normalizeChannels(partial.channels ?? current.channels),
          timing: normalizeTiming(partial.timing ?? current.timing),
        },
      };
    });
  }

  function toggleChannel(id, channel, on) {
    const current = kinds[id] || { enabled: true, channels: ["inbox"], timing: "realtime" };
    const set = new Set(normalizeChannels(current.channels));
    if (on) set.add(channel);
    else set.delete(channel);
    if (!set.size) set.add("inbox");
    patchKind(id, { channels: [...set] });
  }

  async function handleSave(event) {
    event.preventDefault();
    setSaving(true);
    setStatus("");
    try {
      const data = await api.saveNotificationPrefs({
        notification_email: email.trim() || null,
        kinds,
      });
      setEmail(data.notification_email || "");
      setKinds(data.kinds || {});
      setCatalog(Array.isArray(data.catalog) ? data.catalog : catalog);
      setChannels(Array.isArray(data.channels) ? data.channels : channels);
      setMailConfigured(Boolean(data.mail_configured));
      setStatus("Notification preferences saved.");
    } catch (err) {
      setStatus(humanError(err));
    } finally {
      setSaving(false);
    }
  }

  async function handleTest() {
    setTesting(true);
    setStatus("");
    try {
      const result = await api.testNotification({
        kind: "arrived",
        title: "Test notice from the library",
        body: "If you see this in your inbox, notifications are working.",
      });
      setStatus(
        result.emailed
          ? "Test notice landed in your inbox and email was attempted."
          : "Test notice landed in your inbox.",
      );
    } catch (err) {
      setStatus(humanError(err));
    } finally {
      setTesting(false);
    }
  }

  const emailChannel = channels.find((row) => row.id === "email");
  const emailAvailable = Boolean(emailChannel?.available ?? mailConfigured);

  if (!ready) {
    return <p className="muted">Loading notification preferences…</p>;
  }

  return (
    <section
      className="settings-panel"
      id="notifications"
      data-testid="settings-panel-notifications"
      aria-labelledby="settings-notifications-heading"
    >
      <p className="kicker" id="settings-notifications-heading">
        Notifications
      </p>
      <h2>What the house tells you</h2>
      <p className="lede">
        Choose which notices you want, whether they land in the in-app inbox and/or email, and whether email should wait
        for a daily or weekly digest. Email only leaves the house when Mail is configured and you opt in.
      </p>

      <p className="muted">
        Open your{" "}
        <Link to="/inbox">inbox</Link>
        {emailAvailable ? "" : " — owner Mail setup is still needed before email can leave the house"}.
      </p>

      <form className="notifications-prefs-form" onSubmit={handleSave}>
        <label className="field">
          <span>Notification email</span>
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
            aria-label="Notification email"
          />
        </label>

        <ul className="notification-kind-list" aria-label="Notification kinds">
          {catalog.map((row) => {
            const pref = kinds[row.id] || row.default || { enabled: true, channels: ["inbox"], timing: "realtime" };
            const channelSet = new Set(normalizeChannels(pref.channels));
            return (
              <li key={row.id} className="notification-kind-row" data-testid={`notification-kind-${row.id}`}>
                <label className="notification-kind-enable">
                  <input
                    type="checkbox"
                    checked={Boolean(pref.enabled)}
                    onChange={(event) => patchKind(row.id, { enabled: event.target.checked })}
                    aria-label={`Enable ${row.label}`}
                  />
                  <span>
                    <strong>{row.label}</strong>
                    <span className="muted">{row.help}</span>
                  </span>
                </label>
                <div className="notification-kind-channels" role="group" aria-label={`${row.label} channels`}>
                  <label>
                    <input
                      type="checkbox"
                      checked={channelSet.has("inbox")}
                      disabled={!pref.enabled}
                      onChange={(event) => toggleChannel(row.id, "inbox", event.target.checked)}
                    />{" "}
                    In-app
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={channelSet.has("email")}
                      disabled={!pref.enabled || !emailAvailable}
                      onChange={(event) => toggleChannel(row.id, "email", event.target.checked)}
                    />{" "}
                    Email
                  </label>
                </div>
                <label className="notification-kind-timing">
                  <span className="sr-only">Timing for {row.label}</span>
                  <select
                    value={normalizeTiming(pref.timing)}
                    disabled={!pref.enabled}
                    aria-label={`Timing for ${row.label}`}
                    onChange={(event) => patchKind(row.id, { timing: event.target.value })}
                  >
                    {TIMING_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </label>
              </li>
            );
          })}
        </ul>

        <div className="notifications-prefs-actions">
          <button type="submit" className="cta" disabled={saving}>
            {saving ? "Saving…" : "Save preferences"}
          </button>
          {showOwnerTest ? (
            <button type="button" className="cta outline" disabled={testing} onClick={handleTest}>
              {testing ? "Sending…" : "Send test to inbox"}
            </button>
          ) : null}
        </div>
        {status ? <p className="muted" role="status">{status}</p> : null}
      </form>
    </section>
  );
}
