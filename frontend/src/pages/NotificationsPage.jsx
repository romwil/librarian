import { useOutletContext } from "react-router-dom";
import NotificationsPrefsPanel from "../components/NotificationsPrefsPanel.jsx";

/**
 * Member + owner notification preferences (interim Profile surface until Library card).
 */
export default function NotificationsPage() {
  const { user } = useOutletContext() || {};
  const owner = user?.role === "owner";

  return (
    <div className="admin-room notifications-page" data-testid="notifications-page">
      <header className="settings-layout-head">
        <p className="kicker">Profile</p>
        <h1>Notifications</h1>
        <p className="lede">Choose what lands in your inbox and when email may leave the house.</p>
      </header>
      <NotificationsPrefsPanel showOwnerTest={owner} />
    </div>
  );
}
