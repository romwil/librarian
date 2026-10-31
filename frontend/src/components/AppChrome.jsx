import { useEffect, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { stacksNavState } from "../lib/stacksNav.js";
import ProfileMenu from "./ProfileMenu.jsx";
import InboxBadgeButton from "./InboxBadgeButton.jsx";
import { DESK_TAB, DOWNLOADS_NAV, SORTING_NAV } from "../copy.js";
import {
  applyUiFontStep,
  applyUiTheme,
  loadStoredUiFontStep,
  loadStoredUiTheme,
  normalizeUiFontStep,
  normalizeUiTheme,
  persistUiFontStep,
} from "../lib/uiPrefs.js";

export default function AppChrome({ user, features, reviewCount = 0, inboxUnread = 0, children }) {
  const navigate = useNavigate();
  const location = useLocation();
  const stacksNav = stacksNavState(location.pathname, location.search);
  const op = user.role === "owner" || user.role === "op";
  const owner = user.role === "owner";
  const [uiTheme, setUiTheme] = useState(() => loadStoredUiTheme());
  const [fontStep, setFontStep] = useState(() => loadStoredUiFontStep());

  useEffect(() => {
    applyUiTheme(uiTheme);
  }, [uiTheme]);

  useEffect(() => {
    applyUiFontStep(fontStep);
  }, [fontStep]);

  useEffect(() => {
    api
      .prefs()
      .then((data) => {
        if (data.ui_theme != null) {
          const next = normalizeUiTheme(data.ui_theme);
          setUiTheme(next);
          applyUiTheme(next);
        }
        if (data.ui_font_step != null) {
          const next = normalizeUiFontStep(data.ui_font_step);
          setFontStep(next);
          persistUiFontStep(next);
          applyUiFontStep(next);
        }
      })
      .catch(() => {});
  }, [user?.id]);

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

  const sortingLabel = reviewCount > 0 ? `${SORTING_NAV} ${reviewCount}` : SORTING_NAV;
  const deskLabel = reviewCount > 0 ? `${DESK_TAB} ${reviewCount}` : DESK_TAB;

  return (
    <div className="room ambient-off" data-ambient="off">
      <header className="topbar">
        <NavLink to="/" className="brand" end>
          Librarian
        </NavLink>
        {features?.household_name ? <span className="sr-only">{features.household_name}</span> : null}
        <nav className="nav-links" aria-label="Library">
          <NavLink to="/" end className={({ isActive }) => (isActive ? "is-current" : undefined)}>
            Hall
          </NavLink>
          <Link
            to="/browse"
            className={stacksNav.stacks ? "is-current" : undefined}
            aria-current={stacksNav.stacks ? "page" : undefined}
            title="Browse the stacks"
          >
            Stacks
          </Link>
          <NavLink to="/search" className={({ isActive }) => (isActive ? "is-current" : undefined)}>
            Search
          </NavLink>
          <Link
            to="/browse?shelf=favorites"
            className={stacksNav.favorites ? "is-current" : undefined}
            aria-current={stacksNav.favorites ? "page" : undefined}
          >
            Favorites
          </Link>
          <NavLink to="/wanted" className={({ isActive }) => (isActive ? "is-current" : undefined)}>
            Wanted
          </NavLink>
          {op ? (
            <NavLink to="/queue" className={({ isActive }) => (isActive ? "is-current" : undefined)}>
              {DOWNLOADS_NAV}
            </NavLink>
          ) : null}
          {op ? (
            <NavLink to="/review" className={({ isActive }) => (isActive ? "is-current" : undefined)} data-testid="holds-link">
              {sortingLabel}
            </NavLink>
          ) : null}
        </nav>
        <div className="topbar-end">
          <InboxBadgeButton unreadCount={inboxUnread} />
          <ProfileMenu
            user={user}
            owner={owner}
            op={op}
            fontStep={fontStep}
            onFontStepChange={setFontStep}
            uiTheme={uiTheme}
            onThemeChange={setUiTheme}
          />
        </div>
      </header>
      <main id="main" tabIndex={-1}>
        {children}
      </main>
      <nav className="mobile-tabbar" aria-label="Mobile" style={{ "--tab-count": op ? 5 : 4 }}>
        <NavLink to="/" end className={({ isActive }) => (isActive ? "is-current" : undefined)}>
          Hall
        </NavLink>
        <NavLink to="/search" className={({ isActive }) => (isActive ? "is-current" : undefined)}>
          Search
        </NavLink>
        <Link
          to="/browse?shelf=favorites"
          className={stacksNav.favorites ? "is-current" : undefined}
          aria-current={stacksNav.favorites ? "page" : undefined}
        >
          Favorites
        </Link>
        {op ? (
          <NavLink to="/review" className={({ isActive }) => (isActive ? "is-current" : undefined)} data-testid="desk-tab">
            {deskLabel}
          </NavLink>
        ) : null}
        <NavLink to="/card" className={({ isActive }) => (isActive ? "is-current" : undefined)}>
          You
        </NavLink>
      </nav>
    </div>
  );
}
