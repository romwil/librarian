import { useEffect, useRef, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import LampMark from "./LampMark.jsx";

export default function AppChrome({ user, features, reviewCount = 0, children }) {
  const navigate = useNavigate();
  const op = user.role === "owner" || user.role === "op";
  const owner = user.role === "owner";
  const prevCount = useRef(reviewCount);
  const [pulse, setPulse] = useState(false);

  useEffect(() => {
    if (reviewCount > prevCount.current) {
      setPulse(true);
      const timer = window.setTimeout(() => setPulse(false), 1200);
      prevCount.current = reviewCount;
      return () => window.clearTimeout(timer);
    }
    prevCount.current = reviewCount;
    return undefined;
  }, [reviewCount]);

  useEffect(() => {
    function onKey(event) {
      if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) return;
      const tag = String(event.target?.tagName || "").toLowerCase();
      if (tag === "input" || tag === "textarea" || event.target?.isContentEditable) return;
      event.preventDefault();
      const field = document.getElementById("hall-search") || document.getElementById("find-search");
      if (field) {
        field.focus();
        return;
      }
      navigate("/search");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [navigate]);

  async function logout() {
    await api.logout();
    navigate("/login");
  }

  const bagTitle = reviewCount
    ? `Review bag — ${reviewCount} slip${reviewCount === 1 ? "" : "s"} waiting`
    : "Review bag — empty";

  return (
    <div className="room">
      <header className="topbar">
        <NavLink to="/" className="brand" end>
          <LampMark />
          Librarian
        </NavLink>
        <nav className="nav-links" aria-label="Reader">
          <NavLink to="/" end className={({ isActive }) => (isActive ? "is-current" : undefined)}>
            Hall
          </NavLink>
          <NavLink to="/search" className={({ isActive }) => (isActive ? "is-current" : undefined)}>
            Search
          </NavLink>
          <NavLink to="/browse?shelf=favorites" className={({ isActive }) => (isActive ? "is-current" : undefined)}>
            Favorites
          </NavLink>
        </nav>
        <nav className="nav-links nav-ops" aria-label="Stacks and ops">
          <NavLink to="/browse" className={({ isActive }) => (isActive ? "is-current" : undefined)} title="Browse the stacks">
            Stacks
          </NavLink>
          {owner ? (
            <NavLink to="/people" className={({ isActive }) => (isActive ? "is-current" : undefined)}>
              People
            </NavLink>
          ) : null}
          {op ? (
            <NavLink to="/queue" className={({ isActive }) => (isActive ? "is-current" : undefined)}>
              Queue
            </NavLink>
          ) : null}
          {owner ? (
            <NavLink to="/settings" className={({ isActive }) => (isActive ? "is-current" : undefined)}>
              Settings
            </NavLink>
          ) : null}
        </nav>
        <div className="topbar-end">
          {op ? (
            <NavLink
              to="/review"
              className={`bag${pulse ? " is-pulse" : ""}`}
              data-count={reviewCount || undefined}
              aria-label={reviewCount ? `Review bag, ${reviewCount} items` : "Review bag"}
              title={bagTitle}
              data-testid="review-bag"
            >
              <span className="bag-glyph" aria-hidden="true" />
            </NavLink>
          ) : null}
          <button type="button" className="cta ghost" onClick={logout} style={{ padding: "8px 14px" }}>
            {user.display_name}
          </button>
        </div>
      </header>
      <main>{children}</main>
      <nav className="mobile-tabbar" aria-label="Mobile">
        <NavLink to="/" end className={({ isActive }) => (isActive ? "is-current" : undefined)}>
          Hall
        </NavLink>
        <NavLink to="/search" className={({ isActive }) => (isActive ? "is-current" : undefined)}>
          Search
        </NavLink>
        <NavLink to="/browse?shelf=favorites" className={({ isActive }) => (isActive ? "is-current" : undefined)}>
          Favorites
        </NavLink>
        <span className="kicker" style={{ display: "grid", placeItems: "center" }}>
          You
        </span>
      </nav>
      {features?.household_name ? <span className="sr-only">{features.household_name}</span> : null}
    </div>
  );
}
