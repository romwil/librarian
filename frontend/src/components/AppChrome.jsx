import { useEffect, useRef, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import LampMark from "./LampMark.jsx";
import ProfileMenu from "./ProfileMenu.jsx";
import {
  applyUiFontStep,
  applyUiTheme,
  cycleUiTheme,
  loadStoredUiFontStep,
  loadStoredUiTheme,
  normalizeUiFontStep,
  normalizeUiTheme,
  persistUiFontStep,
  themeControlGlyph,
  themePreferenceLabel,
} from "../lib/uiPrefs.js";

export default function AppChrome({ user, features, reviewCount = 0, children }) {
  const navigate = useNavigate();
  const op = user.role === "owner" || user.role === "op";
  const owner = user.role === "owner";
  const prevCount = useRef(reviewCount);
  const [pulse, setPulse] = useState(false);
  const [ambient, setAmbient] = useState("off");
  const [uiTheme, setUiTheme] = useState(() => loadStoredUiTheme());
  const [fontStep, setFontStep] = useState(() => loadStoredUiFontStep());

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

  async function cycleAmbient() {
    const order = ["off", "paper", "lamp"];
    const next = order[(order.indexOf(ambient) + 1) % order.length];
    await setAmbientPref(next);
  }

  async function handleThemeClick() {
    const next = cycleUiTheme(uiTheme);
    setUiTheme(next);
    applyUiTheme(next);
    try {
      await api.savePrefs({ ui_theme: next });
    } catch {
      /* keep local */
    }
  }

  const bagTitle = reviewCount
    ? `Review bag — ${reviewCount} slip${reviewCount === 1 ? "" : "s"} waiting`
    : "Review bag — empty";
  const ambientLabel =
    ambient === "paper" ? "Paper ambient on" : ambient === "lamp" ? "Lamp wash on" : "Ambient off";
  const themeLabel = themePreferenceLabel(uiTheme);

  return (
    <div className={`room ambient-${ambient}`} data-ambient={ambient}>
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
            <NavLink to="/maintain" className={({ isActive }) => (isActive ? "is-current" : undefined)}>
              Maintain
            </NavLink>
          ) : null}
          {owner ? (
            <NavLink to="/settings" className={({ isActive }) => (isActive ? "is-current" : undefined)}>
              Settings
            </NavLink>
          ) : null}
        </nav>
        <div className="topbar-end">
          <button
            type="button"
            className="cta ghost compact ambient-toggle"
            onClick={cycleAmbient}
            title={ambientLabel}
            aria-label={ambientLabel}
            data-testid="ambient-toggle"
          >
            Lamp
          </button>
          <button
            type="button"
            className="cta ghost compact theme-toggle"
            onClick={handleThemeClick}
            title={`${themeLabel}. Click to change.`}
            aria-label={`Theme: ${themeLabel}. Click to change.`}
            data-testid="theme-toggle"
          >
            <span aria-hidden="true">{themeControlGlyph(uiTheme)}</span>
          </button>
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
