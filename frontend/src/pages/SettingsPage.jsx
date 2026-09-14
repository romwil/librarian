import { useEffect, useState } from "react";
import { api } from "../api.js";

const FIELDS = [
  ["sabnzbd_url", "SABnzbd URL"],
  ["sabnzbd_api_key", "SABnzbd API key", true],
  ["nzbfinder_url", "NZBFinder URL"],
  ["nzbfinder_api_token", "NZBFinder token", true],
  ["books_root", "Books root"],
  ["magazines_root", "Magazines root"],
  ["comics_root", "Comics root"],
  ["audiobooks_root", "Audiobooks root"],
  ["incoming_music_root", "Incoming music"],
  ["music_root", "Plexamp music"],
  ["audiobook_target", "Audiobook target"],
  ["household_name", "Household name"],
];

export default function SettingsPage() {
  const [settings, setSettings] = useState(null);
  const [saved, setSaved] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    api
      .settings()
      .then((data) => setSettings(data.settings))
      .catch((err) => setError(err.message));
  }, []);

  async function onSubmit(event) {
    event.preventDefault();
    setError("");
    try {
      const data = await api.saveSettings(settings);
      setSettings(data.settings);
      setSaved("Saved.");
    } catch (err) {
      setError(err.message);
    }
  }

  if (!settings) return <p className="muted">Lamp is warming…</p>;

  return (
    <div className="admin-room">
      <p className="eyebrow">Owner</p>
      <h1>Settings</h1>
      <p className="lede">settings.json wins. Secrets stay on the host.</p>
      {error ? <p className="alert">{error}</p> : null}
      {saved ? <p className="muted">{saved}</p> : null}
      <form className="settings-form" onSubmit={onSubmit}>
        {FIELDS.map(([key, label, secret]) => (
          <label key={key} className="login-field">
            {label}
            {key === "audiobook_target" ? (
              <select value={settings[key] || "plex"} onChange={(e) => setSettings({ ...settings, [key]: e.target.value })}>
                <option value="plex">Plex Audiobooks</option>
                <option value="audiobookshelf">Audiobookshelf</option>
                <option value="librarian_only">Librarian only</option>
              </select>
            ) : (
              <input
                type={secret ? "password" : "text"}
                value={settings[key] || ""}
                placeholder={secret && settings[`${key}_set`] ? "saved" : ""}
                onChange={(e) => setSettings({ ...settings, [key]: e.target.value })}
              />
            )}
          </label>
        ))}
        <button type="submit" className="login-primary">
          Save
        </button>
      </form>
    </div>
  );
}
