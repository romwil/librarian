import { useEffect, useState } from "react";
import { api } from "../api.js";
import {
  FONT_STEP_MAX,
  applyUiFontStep,
  applyUiTheme,
  loadStoredUiFontStep,
  loadStoredUiTheme,
  normalizeUiFontStep,
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
  { value: "paper", label: "Paper dust" },
  { value: "lamp", label: "Lamp wash" },
];

/** Personal appearance prefs — same store as the profile menu (`api.prefs`). */
export default function AppearancePrefsPanel() {
  const [uiTheme, setUiTheme] = useState(() => loadStoredUiTheme());
  const [fontStep, setFontStep] = useState(() => loadStoredUiFontStep());
  const [ambient, setAmbient] = useState("off");
  const [note, setNote] = useState("");

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
        setAmbient(data.ambient || "off");
      })
      .catch(() => {
        /* keep localStorage defaults */
      });
  }, []);

  async function save(partial) {
    setNote("");
    try {
      const saved = await api.savePrefs(partial);
      if (saved.ui_theme != null) {
        const next = normalizeUiTheme(saved.ui_theme);
        setUiTheme(next);
        applyUiTheme(next);
      }
      if (saved.ui_font_step != null) {
        const next = normalizeUiFontStep(saved.ui_font_step);
        setFontStep(next);
        persistUiFontStep(next);
        applyUiFontStep(next);
      }
      if (saved.ambient != null) setAmbient(saved.ambient);
      setNote("Saved to your profile.");
    } catch (error) {
      setNote(error.message || "Could not save appearance.");
    }
  }

  return (
    <details className="more-settings" open data-testid="appearance-prefs">
      <summary className="kicker">Your appearance</summary>
      <p className="lede">
        Personal to you — theme, text size, and room wash. Same controls as the profile menu. Quiet hours stay under
        household ops below.
      </p>
      <div className="field">
        <span className="kicker">Theme</span>
        <div className="settings-appearance-options" role="radiogroup" aria-label="Theme">
          {THEME_OPTIONS.map((option) => (
            <label
              key={option.value}
              className={`settings-theme-option${uiTheme === option.value ? " selected" : ""}`}
            >
              <input
                type="radio"
                name="settings-ui-theme"
                value={option.value}
                checked={uiTheme === option.value}
                data-testid={`settings-theme-${option.value}`}
                onChange={() => {
                  applyUiTheme(option.value);
                  setUiTheme(option.value);
                  save({ ui_theme: option.value });
                }}
              />
              <span>{themePreferenceLabel(option.value)}</span>
            </label>
          ))}
        </div>
      </div>
      <div className="field">
        <span className="kicker">Text size</span>
        <label className="settings-font-slider" data-testid="settings-font-slider">
          <span className="profile-font-label">
            {fontStep === 0 ? "Default" : `+${fontStep} larger`}
          </span>
          <input
            type="range"
            min={0}
            max={FONT_STEP_MAX}
            step={1}
            value={fontStep}
            aria-label="Text size"
            onChange={(event) => {
              const next = applyUiFontStep(event.target.value);
              persistUiFontStep(next);
              setFontStep(next);
              save({ ui_font_step: next });
            }}
          />
        </label>
      </div>
      <div className="field">
        <span className="kicker">Room wash</span>
        <div className="settings-appearance-options" role="radiogroup" aria-label="Ambient">
          {AMBIENT_OPTIONS.map((option) => (
            <label
              key={option.value}
              className={`settings-theme-option${ambient === option.value ? " selected" : ""}`}
            >
              <input
                type="radio"
                name="settings-ambient"
                value={option.value}
                checked={ambient === option.value}
                data-testid={`settings-ambient-${option.value}`}
                onChange={() => {
                  setAmbient(option.value);
                  save({ ambient: option.value });
                }}
              />
              <span>{option.label}</span>
            </label>
          ))}
        </div>
      </div>
      {note ? <p className="muted">{note}</p> : null}
    </details>
  );
}
