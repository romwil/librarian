import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import {
  FONT_STEP_MAX,
  applyUiFontStep,
  applyUiTheme,
  normalizeUiTheme,
  persistUiFontStep,
  themePreferenceLabel,
} from "../lib/uiPrefs.js";

const THEME_OPTIONS = [
  { value: "lights_up", label: "Lights Up" },
  { value: "lights_down", label: "Lights Down" },
  { value: "system", label: "Match system" },
];

const AMBIENT_OPTIONS = [
  { value: "off", label: "Off" },
  { value: "paper", label: "Paper" },
  { value: "lamp", label: "Lamp wash" },
];

/**
 * Profile chip + anchored menu of personal prefs.
 * Sections: appearance → room → links → Logout last.
 */
export default function ProfileMenu({
  user,
  fontStep = 0,
  onFontStepChange,
  uiTheme = "system",
  onThemeChange,
  ambient = "off",
  onAmbientChange,
  owner = false,
  op = false,
}) {
  const navigate = useNavigate();
  const rootRef = useRef(null);
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!open) return undefined;
    function eventInsideMenu(event) {
      const root = rootRef.current;
      if (!root) return false;
      // Range inputs (and some UA widgets) can retarget so event.target is
      // outside the menu even when the gesture started inside — prefer path.
      const path = typeof event.composedPath === "function" ? event.composedPath() : [];
      if (path.length > 0) return path.includes(root);
      const target = event.target;
      return target instanceof Node && root.contains(target);
    }
    function onPointerDown(event) {
      if (!eventInsideMenu(event)) setOpen(false);
    }
    function onKey(event) {
      if (event.key === "Escape") setOpen(false);
    }
    document.addEventListener("pointerdown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function handleLogout() {
    setOpen(false);
    try {
      await api.logout();
    } catch {
      // Still leave the room.
    }
    navigate("/login", { replace: true });
  }

  function handleFontChange(event) {
    const next = applyUiFontStep(event.target.value);
    persistUiFontStep(next);
    onFontStepChange?.(next);
    api.savePrefs({ ui_font_step: next }).catch(() => {
      /* keep local */
    });
  }

  function handleThemePick(value) {
    const next = normalizeUiTheme(value);
    applyUiTheme(next);
    onThemeChange?.(next);
    api.savePrefs({ ui_theme: next }).catch(() => {
      /* keep local */
    });
  }

  function handleAmbientPick(value) {
    onAmbientChange?.(value);
  }

  const roleLabel = String(user?.role || "reader").toUpperCase();
  const initials = String(user?.display_name || "?")
    .trim()
    .slice(0, 1)
    .toUpperCase();
  const showHouseholdLinks = owner || op;

  return (
    <div className="profile-menu" ref={rootRef} data-testid="profile-menu">
      <button
        type="button"
        className="profile-menu-trigger"
        data-testid="profile-menu-trigger"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((value) => !value)}
      >
        <span className="profile-menu-avatar" aria-hidden="true">
          {initials}
        </span>
        <span className="profile-menu-name">{user.display_name}</span>
        <span className="profile-menu-role">{roleLabel}</span>
      </button>
      {open ? (
        <div
          className="profile-menu-panel"
          role="menu"
          data-testid="profile-menu-panel"
          onPointerDown={(event) => event.stopPropagation()}
          onMouseDown={(event) => event.stopPropagation()}
        >
          <p className="profile-menu-meta">
            {user.display_name}
            <span>{roleLabel}</span>
          </p>

          <div className="profile-menu-section" data-testid="profile-theme-section">
            <p className="profile-menu-section-label">Theme</p>
            <div className="profile-chip-row" role="radiogroup" aria-label="Theme">
              {THEME_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  role="radio"
                  aria-checked={uiTheme === option.value}
                  className={`profile-chip${uiTheme === option.value ? " is-selected" : ""}`}
                  data-testid={`profile-theme-${option.value}`}
                  title={themePreferenceLabel(option.value)}
                  onClick={() => handleThemePick(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          <label className="profile-font-control" data-testid="profile-font-slider">
            <span className="profile-font-label">
              Text size
              <span className="profile-font-value">
                {fontStep === 0 ? "Default" : `+${fontStep}`}
              </span>
            </span>
            <input
              type="range"
              min={0}
              max={FONT_STEP_MAX}
              step={1}
              value={fontStep}
              aria-valuemin={0}
              aria-valuemax={FONT_STEP_MAX}
              aria-valuenow={fontStep}
              aria-label="Text size. Far left is the default size; slide right to enlarge."
              onChange={handleFontChange}
            />
          </label>

          <div className="profile-menu-section" data-testid="profile-ambient-section">
            <p className="profile-menu-section-label">Room wash</p>
            <div className="profile-chip-row" role="radiogroup" aria-label="Ambient room wash">
              {AMBIENT_OPTIONS.map((option) => (
                <button
                  key={option.value}
                  type="button"
                  role="radio"
                  aria-checked={ambient === option.value}
                  className={`profile-chip${ambient === option.value ? " is-selected" : ""}`}
                  data-testid={`profile-ambient-${option.value}`}
                  onClick={() => handleAmbientPick(option.value)}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>

          {showHouseholdLinks ? (
            <div className="profile-menu-section profile-menu-links">
              {owner ? (
                <Link
                  to="/maintain"
                  className="profile-menu-link"
                  role="menuitem"
                  onClick={() => setOpen(false)}
                >
                  Maintain
                </Link>
              ) : null}
              {owner ? (
                <Link
                  to="/settings"
                  className="profile-menu-link"
                  role="menuitem"
                  onClick={() => setOpen(false)}
                >
                  Household Settings
                </Link>
              ) : null}
              {owner ? (
                <Link
                  to="/people"
                  className="profile-menu-link"
                  role="menuitem"
                  onClick={() => setOpen(false)}
                >
                  People
                </Link>
              ) : null}
              {op ? (
                <Link
                  to="/queue"
                  className="profile-menu-link"
                  role="menuitem"
                  onClick={() => setOpen(false)}
                >
                  Queue
                </Link>
              ) : null}
            </div>
          ) : null}

          <button
            type="button"
            className="profile-menu-link profile-menu-logout"
            role="menuitem"
            data-testid="logout-button"
            onClick={handleLogout}
          >
            Logout
          </button>
        </div>
      ) : null}
    </div>
  );
}
