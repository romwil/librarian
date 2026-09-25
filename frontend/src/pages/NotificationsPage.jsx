import { useEffect, useState } from "react";
import { useOutletContext } from "react-router-dom";
import NewsletterPushPanel from "../components/NewsletterPushPanel.jsx";
import NotificationsPrefsPanel from "../components/NotificationsPrefsPanel.jsx";
import { api } from "../api.js";

/**
 * Member + owner notification preferences (interim Profile surface until Library card).
 */
export default function NotificationsPage() {
  const { user } = useOutletContext() || {};
  const owner = user?.role === "owner";
  const [mailConfigured, setMailConfigured] = useState(false);

  useEffect(() => {
    if (!owner) return undefined;
    let cancelled = false;
    api
      .notificationPrefs()
      .then((data) => {
        if (!cancelled) setMailConfigured(Boolean(data.mail_configured));
      })
      .catch(() => {
        if (!cancelled) setMailConfigured(false);
      });
    return () => {
      cancelled = true;
    };
  }, [owner]);

  return (
    <div className="admin-room notifications-page" data-testid="notifications-page">
      <header className="settings-layout-head">
        <p className="kicker">Profile</p>
        <h1>Notifications</h1>
        <p className="lede">
          Choose what lands in your inbox, opt into the library letter, and when email may leave the house.
        </p>
      </header>
      {owner ? <NewsletterPushPanel mailConfigured={mailConfigured} /> : null}
      <NotificationsPrefsPanel showOwnerTest={owner} />
    </div>
  );
}
