import { useEffect, useState } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { stacksNavState } from "../lib/stacksNav.js";
import ProfileMenu from "./ProfileMenu.jsx";
import InboxBadgeButton from "./InboxBadgeButton.jsx";
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
  const [ambient, setAmbient] = useState("off");
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
        setAmbient(data.ambient || "off");
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
      .catch(() => setAmbient("off"));
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

  async function setAmbientPref(next) {
    setAmbient(next);
    try {
      await api.savePrefs({ ambient: next });
    } catch {
      /* keep local */
    }
  }

  const holdsLabel = reviewCount > 0 ? `Holds ${reviewCount}` : "Holds";

  return (
    <div className={`room ambient-${ambient}`} data-ambient={ambient}>
      <a className="skip-link" href="#main">
        Skip to library
      </a>
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
              Downloads
            </NavLink>
          ) : null}
          {op ? (
            <NavLink to="/review" className={({ isActive }) => (isActive ? "is-current" : undefined)} data-testid="holds-link">
              {holdsLabel}
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
            ambient={ambient}
            onAmbientChange={setAmbientPref}
          />
        </div>
      </header>
      <main id="main" tabIndex={-1}>
        {children}
      </main>
      <nav className="mobile-tabbar" aria-label="Mobile" style={{ "--tab-count": 6 }}>
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
        <NavLink to="/card" className={({ isActive }) => (isActive ? "is-current" : undefined)}>
          Library card
        </NavLink>
      </nav>
    </div>
  );
}
