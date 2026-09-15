import { useEffect, useState } from "react";
import { api } from "../api.js";
import { FieldLabel } from "../components/FieldHelp.jsx";
import SetupWizard from "../components/SetupWizard.jsx";
import { FIELD_HELP, humanError, setupComplete, setupStepComplete } from "../copy.js";

const MORE_FIELDS = [
  ["audiobook_target", "Audiobook target"],
  ["llm_base_url", "LLM base URL"],
  ["llm_api_key", "LLM API key", true],
  ["llm_model", "LLM model"],
  ["household_name", "Household name"],
];

export default function SettingsPage() {
  const [settings, setSettings] = useState(null);
  const [saved, setSaved] = useState("");
  const [error, setError] = useState("");
  const [ping, setPing] = useState("");
  const [step, setStep] = useState(0);

  useEffect(() => {
    api
      .settings()
      .then((data) => {
        setSettings(data.settings);
        const next = [0, 1, 2, 3].find((index) => !setupStepComplete(data.settings, index));
        setStep(next == null ? 0 : next);
      })
      .catch((err) => setError(humanError(err)));
  }, []);

  function patch(key, value) {
    setSettings((prev) => ({ ...prev, [key]: value }));
  }

  async function onSubmit(event) {
    event.preventDefault();
    setError("");
    try {
      const data = await api.saveSettings(settings);
      setSettings(data.settings);
      setSaved("Saved.");
    } catch (err) {
      setError(humanError(err));
    }
  }

  if (!settings && !error) return <p className="muted admin-room">Lamp is warming…</p>;
  if (!settings) {
    return (
      <div className="admin-room">
        <p className="alert">{error}</p>
      </div>
    );
  }

  const done = setupComplete(settings);

  return (
    <div className="admin-room">
      <p className="kicker">Owner</p>
      <h1>Settings</h1>
      <p className="lede">
        {done
          ? "The house is already configured. These steps stay here if you need to change a path or token."
          : "Four short steps. The Hall stays open while you fill them in."}
      </p>
      {error ? <p className="alert">{error}</p> : null}
      {saved ? <p className="muted">{saved}</p> : null}
      {ping ? <p className={/ok/i.test(ping) ? "muted" : "callout"}>{ping}</p> : null}
      <form className="settings-form" onSubmit={onSubmit}>
        <SetupWizard settings={settings} onChange={patch} step={step} setStep={setStep} />
        <details className="more-settings">
          <summary className="kicker">More — listen target, LLM, household name</summary>
          {MORE_FIELDS.map(([key, label, secret]) => (
            <div key={key} className="field">
              <FieldLabel htmlFor={`setting-${key}`} label={label} help={FIELD_HELP[key]} />
              {key === "audiobook_target" ? (
                <select
                  id={`setting-${key}`}
                  value={settings[key] || "plex"}
                  onChange={(e) => patch(key, e.target.value)}
                >
                  <option value="plex">Plex Audiobooks</option>
                  <option value="audiobookshelf">Audiobookshelf</option>
                  <option value="librarian_only">Librarian only</option>
                </select>
              ) : (
                <input
                  id={`setting-${key}`}
                  type={secret ? "password" : "text"}
                  value={settings[key] || ""}
                  placeholder={secret && settings[`${key}_set`] ? "saved" : ""}
                  onChange={(e) => patch(key, e.target.value)}
                />
              )}
            </div>
          ))}
        </details>
        <div className="cta-row">
          <button type="submit" className="cta">
            Save
          </button>
          <button
            type="button"
            className="cta outline"
            onClick={async () => {
              setPing("");
              try {
                const data = await api.pingIndexer();
                setPing(
                  data.ok
                    ? `NZBFinder ok — ${data.server} (${data.category_count} categories)`
                    : humanError(data.error || "Ping failed"),
                );
              } catch (err) {
                setPing(humanError(err));
              }
            }}
          >
            Ping NZBFinder
          </button>
        </div>
      </form>
    </div>
  );
}
