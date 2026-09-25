import { NavLink } from "react-router-dom";
import { formatUnreadBadge } from "../lib/notificationInbox.js";

/**
 * Top-chrome inbox entry with unread badge.
 */
export default function InboxBadgeButton({ unreadCount = 0, className = "inbox-badge-btn" }) {
  const badge = formatUnreadBadge(unreadCount);
  return (
    <NavLink
      to="/inbox"
      className={({ isActive }) => `${className}${isActive ? " is-active" : ""}`}
      aria-label={badge ? `Inbox, ${unreadCount} unread` : "Inbox"}
      title={badge ? `Inbox (${badge})` : "Inbox"}
      data-testid="topbar-inbox-button"
    >
      <span className="inbox-badge-glyph" aria-hidden="true">
        ✉
      </span>
      {badge ? (
        <span className="inbox-unread-badge" data-testid="topbar-inbox-badge">
          {badge}
        </span>
      ) : null}
    </NavLink>
  );
}
