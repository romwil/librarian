import { useEffect, useRef, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { api } from "../api.js";
import { FieldLabel } from "../components/FieldHelp.jsx";
import { SetupFields } from "../components/SetupWizard.jsx";
import AboutPanel from "../components/AboutPanel.jsx";
import RssPanel from "../components/RssPanel.jsx";
import { FIELD_HELP, WATCH_FOLDER_LEDE, humanError, setupComplete, setupStepComplete } from "../copy.js";
import { SETTINGS_NAV, settingsNavFromHash, settingsNavHref } from "../lib/settingsNav.js";
import LlmSettingsPanel from "../components/LlmSettingsPanel.jsx";
import AppearancePrefsPanel from "../components/AppearancePrefsPanel.jsx";
import MailSettingsPanel from "../components/MailSettingsPanel.jsx";
import NotificationsPrefsPanel from "../components/NotificationsPrefsPanel.jsx";

const MORE_FIELDS = [
  ["audiobook_target", "Audiobook target"],
  ["hardcover_api_token", "Hardcover token", true],
  ["comicvine_api_key", "Comic Vine key", true],
  ["komga_url", "Komga URL"],
  ["komga_api_key", "Komga API key", true],
  ["komga_library_id", "Komga library id"],
  ["audiobookshelf_url", "Audiobookshelf URL"],
  ["audiobookshelf_api_token", "Audiobookshelf token", true],
  ["household_name", "Household name"],
];

export default function SettingsPage() {
  const { user } = useOutletContext() || {};
  const [settings, setSettings] = useState(null);
  const [saved, setSaved] = useState("");
  const [error, setError] = useState("");
  const [ping, setPing] = useState("");
  const [absMatch, setAbsMatch] = useState(null);
  const [absNote, setAbsNote] = useState("");
  const [matching, setMatching] = useState(false);
  const [activeSection, setActiveSection] = useState("downloader");
  const formRef = useRef(null);

  useEffect(() => {
    if (user && user.role !== "owner") return;
    api
      .settings()
      .then((data) => {
        setSettings(data.settings);
        setAbsMatch(data.abs_match || null);
        const fromHash = settingsNavFromHash(window.location.hash);
        if (fromHash) {
          setActiveSection(fromHash.id);
        } else {
          const next = [0, 1, 2, 3].find((index) => !setupStepComplete(data.settings, index));
          setActiveSection(next != null ? SETTINGS_NAV.find((row) => row.step === next)?.id || "downloader" : "downloader");
        }
      })
      .catch((err) => setError(humanError(err)));
  }, [user]);

  useEffect(() => {
    if (typeof window === "undefined") return undefined;
    function onHash() {
      const item = settingsNavFromHash(window.location.hash);
      if (!item) return;
      setActiveSection(item.id);
      const targetId = item.id === "about" && window.location.hash === "#release-notes" ? "release-notes" : item.id;
      window.requestAnimationFrame(() => {
        document.getElementById(targetId)?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
    onHash();
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  function goToSection(item) {
    setActiveSection(item.id);
    if (typeof window !== "undefined") {
      window.history.replaceState(null, "", settingsNavHref(item));
    }
    window.requestAnimationFrame(() => {
      const targetId = item.id === "about" ? "about" : item.id;
      document.getElementById(targetId)?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function patch(key, value) {
    setSettings((prev) => ({ ...prev, [key]: value }));
  }

  async function onSubmit(event) {
    event.preventDefault();
    setError("");
    try {
      const data = await api.saveSettings(settings);
      setSettings(data.settings);
      setAbsMatch(data.abs_match || absMatch);
      setSaved("Saved.");
    } catch (err) {
      setError(humanError(err));
    }
  }

  if (user && user.role !== "owner") {
    return (
      <div className="admin-room settings-page">
        <p className="alert">Settings are for the household owner.</p>
        <Link className="cta outline" to="/">
          Back to the Hall
        </Link>
      </div>
    );
  }

  if (!settings && !error) return <p className="muted admin-room settings-page">Lamp is warming…</p>;
  if (!settings) {
    return (
      <div className="admin-room settings-page">
        <p className="alert">{error}</p>
      </div>
    );
  }

  const done = setupComplete(settings);

  return (
    <div className="admin-room settings-page settings-layout" data-testid="settings-page">
      <header className="settings-layout-head">
        <p className="kicker">Owner</p>
        <h1>Settings</h1>
        <p className="lede">
          {done
            ? "Credentials and paths for the house. Library grooming (scan, enrich, add on disk) lives on Maintain."
            : "Fill Downloader, Indexers, and Shelves first. Jump any section from the list — no Next/Previous steps."}
        </p>
      </header>

      <div className="settings-layout-body">
        <nav className="settings-section-nav" aria-label="Settings sections" data-testid="settings-section-nav">
          <ol className="settings-nav-list">
            {SETTINGS_NAV.map((item) => {
              const on = activeSection === item.id;
              const doneStep = item.kind === "setup" && typeof item.step === "number" && setupStepComplete(settings, item.step);
              return (
                <li key={item.id}>
                  <button
                    type="button"
                    className={`settings-nav-item${on ? " is-on" : ""}${doneStep ? " is-done" : ""}`}
                    data-testid={`settings-nav-${item.id}`}
                    aria-current={on ? "true" : undefined}
                    onClick={() => goToSection(item)}
                  >
                    {item.label}
                  </button>
                </li>
              );
            })}
          </ol>
        </nav>

        <div className="settings-layout-main">
          {error ? <p className="alert">{error}</p> : null}
          {saved ? <p className="muted">{saved}</p> : null}
          {ping ? <p className={/ok/i.test(ping) ? "muted" : "callout"}>{ping}</p> : null}

          <form className="settings-form" ref={formRef} onSubmit={onSubmit}>
            {activeSection === "appearance" ? (
              <section className="settings-panel" id="appearance" data-testid="settings-panel-appearance">
                <AppearancePrefsPanel />
              </section>
            ) : null}

            {activeSection === "downloader" ? <SetupFields step="downloader" settings={settings} onChange={patch} /> : null}

            {activeSection === "indexers" ? (
              <>
                <SetupFields step="indexers" settings={settings} onChange={patch} />
                <section className="settings-panel settings-extra-indexers" data-testid="settings-extra-indexers" aria-labelledby="extra-indexers-heading">
                  <p className="kicker" id="extra-indexers-heading">
                    More Newznab hosts
                  </p>
                  <h2>Additional indexers</h2>
                  <p className="lede">
                    NZBFinder stays first. Add other Newznab v2 JSON hosts; Find merges hits and keeps going if one host
                    fails. Save after editing.
                  </p>
                  {(settings.extra_indexers || []).length === 0 ? (
                    <p className="muted" data-testid="extra-indexers-empty">
                      No extra hosts yet. Add one to search more than NZBFinder.
                    </p>
                  ) : null}
                  {(settings.extra_indexers || []).map((row, index) => (
                    <div key={row.id || index} className="extra-indexer" data-testid="extra-indexer-row">
                      <div className="field">
                        <FieldLabel htmlFor={`extra-name-${index}`} label="Name" />
                        <input
                          id={`extra-name-${index}`}
                          value={row.name || ""}
                          onChange={(event) => {
                            const next = [...(settings.extra_indexers || [])];
                            next[index] = { ...row, name: event.target.value };
                            patch("extra_indexers", next);
                          }}
                        />
                      </div>
                      <div className="field">
                        <FieldLabel htmlFor={`extra-url-${index}`} label="URL" help={FIELD_HELP.extra_indexer_url} />
                        <input
                          id={`extra-url-${index}`}
                          value={row.url || ""}
                          onChange={(event) => {
                            const next = [...(settings.extra_indexers || [])];
                            next[index] = { ...row, url: event.target.value };
                            patch("extra_indexers", next);
                          }}
                          spellCheck={false}
                        />
                      </div>
                      <div className="field">
                        <FieldLabel htmlFor={`extra-token-${index}`} label="API token" help={FIELD_HELP.extra_indexer_token} />
                        <input
                          id={`extra-token-${index}`}
                          type="password"
                          value={row.api_token || ""}
                          placeholder={row.api_token_set ? "saved" : ""}
                          onChange={(event) => {
                            const next = [...(settings.extra_indexers || [])];
                            next[index] = { ...row, api_token: event.target.value };
                            patch("extra_indexers", next);
                          }}
                        />
                      </div>
                      <div className="field field-check">
                        <label htmlFor={`extra-on-${index}`}>
                          <input
                            id={`extra-on-${index}`}
                            type="checkbox"
                            checked={row.enabled !== false}
                            onChange={(event) => {
                              const next = [...(settings.extra_indexers || [])];
                              next[index] = { ...row, enabled: event.target.checked };
                              patch("extra_indexers", next);
                            }}
                          />
                          Enabled
                        </label>
                        <button
                          type="button"
                          className="cta ghost compact"
                          data-testid="extra-indexer-remove"
                          onClick={() =>
                            patch(
                              "extra_indexers",
                              (settings.extra_indexers || []).filter((_, item) => item !== index),
                            )
                          }
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  ))}
                  <div className="cta-row">
                    <button
                      type="button"
                      className="cta outline"
                      data-testid="extra-indexer-add"
                      onClick={() =>
                        patch("extra_indexers", [
                          ...(settings.extra_indexers || []),
                          { id: `extra-${Date.now()}`, name: "", url: "", api_token: "", enabled: true },
                        ])
                      }
                    >
                      Add indexer
                    </button>
                    <button
                      type="button"
                      className="cta outline"
                      data-testid="settings-ping-indexer"
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
                </section>
                <section className="settings-panel settings-rss" id="rss" data-testid="settings-rss" aria-labelledby="settings-rss-heading">
                  <p className="kicker" id="settings-rss-heading">
                    RSS
                  </p>
                  <h2>Indexer feeds</h2>
                  <RssPanel />
                </section>
                <section className="settings-panel" data-testid="settings-show-categories" aria-labelledby="settings-categories-heading">
                  <p className="kicker" id="settings-categories-heading">
                    Categories
                  </p>
                  <h2>Show categories</h2>
                  <p className="lede">
                    Off keeps Find on books, magazines, comics, audiobooks, and music. On, Discover can peruse every feed
                    the indexer lists — including Movies, TV, and XXX. Those do not land on The Hall.
                  </p>
                  <div className="field field-check">
                    <label htmlFor="setting-show_extra_categories">
                      <input
                        id="setting-show_extra_categories"
                        type="checkbox"
                        checked={Boolean(settings.show_extra_categories)}
                        onChange={(e) => patch("show_extra_categories", e.target.checked)}
                      />
                      Show categories (beyond normal Librarian use)
                    </label>
                  </div>
                  <div className="field">
                    <FieldLabel htmlFor="setting-radarr_url" label="Radarr URL" help={FIELD_HELP.radarr_url} />
                    <input
                      id="setting-radarr_url"
                      value={settings.radarr_url || ""}
                      onChange={(e) => patch("radarr_url", e.target.value)}
                      spellCheck={false}
                    />
                  </div>
                  <div className="field">
                    <FieldLabel htmlFor="setting-radarr_api_key" label="Radarr API key" help={FIELD_HELP.radarr_api_key} />
                    <input
                      id="setting-radarr_api_key"
                      type="password"
                      value={settings.radarr_api_key || ""}
                      placeholder={settings.radarr_api_key_set ? "saved" : ""}
                      onChange={(e) => patch("radarr_api_key", e.target.value)}
                    />
                  </div>
                  <div className="field">
                    <FieldLabel htmlFor="setting-sonarr_url" label="Sonarr URL" help={FIELD_HELP.sonarr_url} />
                    <input
                      id="setting-sonarr_url"
                      value={settings.sonarr_url || ""}
                      onChange={(e) => patch("sonarr_url", e.target.value)}
                      spellCheck={false}
                    />
                  </div>
                  <div className="field">
                    <FieldLabel htmlFor="setting-sonarr_api_key" label="Sonarr API key" help={FIELD_HELP.sonarr_api_key} />
                    <input
                      id="setting-sonarr_api_key"
                      type="password"
                      value={settings.sonarr_api_key || ""}
                      placeholder={settings.sonarr_api_key_set ? "saved" : ""}
                      onChange={(e) => patch("sonarr_api_key", e.target.value)}
                    />
                  </div>
                  <div className="field">
                    <FieldLabel htmlFor="setting-sab_movie_category" label="SAB movie category" help={FIELD_HELP.sab_movie_category} />
                    <input
                      id="setting-sab_movie_category"
                      value={settings.sab_movie_category || ""}
                      onChange={(e) => patch("sab_movie_category", e.target.value)}
                      spellCheck={false}
                    />
                  </div>
                  <div className="field">
                    <FieldLabel htmlFor="setting-sab_tv_category" label="SAB TV category" help={FIELD_HELP.sab_tv_category} />
                    <input
                      id="setting-sab_tv_category"
                      value={settings.sab_tv_category || ""}
                      onChange={(e) => patch("sab_tv_category", e.target.value)}
                      spellCheck={false}
                    />
                  </div>
                </section>
              </>
            ) : null}

            {activeSection === "shelves" ? <SetupFields step="shelves" settings={settings} onChange={patch} /> : null}
            {activeSection === "shelving" ? <SetupFields step="shelving" settings={settings} onChange={patch} /> : null}

            {activeSection === "llm" ? (
              <section className="settings-panel" id="llm" data-testid="settings-panel-llm">
                <p className="kicker">Language model</p>
                <h2>OpenAI, Anthropic, or Gemini</h2>
                <LlmSettingsPanel settings={settings} onChange={setSettings} />
              </section>
            ) : null}

            {activeSection === "mail" ? (
              <MailSettingsPanel settings={settings} onChange={setSettings} />
            ) : null}

            {activeSection === "notifications" ? (
              <NotificationsPrefsPanel showOwnerTest />
            ) : null}

            {activeSection === "integrations" ? (
              <section className="settings-panel" id="integrations" data-testid="settings-panel-integrations">
                <p className="kicker">Integrations</p>
                <h2>Listen target, enrichment keys, household name</h2>
                <p className="lede">Optional tokens for covers and metadata. Save when done.</p>
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
                {absMatch ? (
                  <p className="muted" data-testid="abs-match-count">
                    {absMatch.matched} of {absMatch.audiobooks} audiobooks matched to the player
                  </p>
                ) : null}
                <div className="cta-row">
                  <button
                    type="button"
                    className="cta outline"
                    disabled={matching || !settings.audiobookshelf_api_token_set}
                    onClick={async () => {
                      setAbsNote("");
                      setMatching(true);
                      try {
                        const data = await api.absMatch();
                        setAbsMatch({ matched: data.matched, audiobooks: data.audiobooks });
                        setAbsNote(
                          data.called
                            ? `Matched ${data.updated} more · ${data.matched} of ${data.audiobooks} on the player`
                            : "Add an Audiobookshelf URL and token, then match.",
                        );
                      } catch (err) {
                        setAbsNote(humanError(err));
                      } finally {
                        setMatching(false);
                      }
                    }}
                  >
                    {matching ? "Matching…" : "Match Audiobookshelf"}
                  </button>
                </div>
                {absNote ? <p className={/Matched /.test(absNote) ? "muted" : "alert"}>{absNote}</p> : null}
              </section>
            ) : null}

            {activeSection === "household" ? (
              <section className="settings-panel" id="household" data-testid="settings-panel-household">
                <p className="kicker">Household</p>
                <h2>Quiet hours</h2>
                <p className="lede">
                  Defer unpack and convert during a household window. Review shows Queued for tonight. Owner and ops can
                  change this.
                </p>
                <div className="field field-check">
                  <label htmlFor="setting-quiet_hours_enabled">
                    <input
                      id="setting-quiet_hours_enabled"
                      type="checkbox"
                      checked={Boolean(settings.quiet_hours_enabled)}
                      onChange={(e) => patch("quiet_hours_enabled", e.target.checked)}
                    />
                    Enable quiet hours Organize
                  </label>
                </div>
                <div className="field">
                  <FieldLabel htmlFor="setting-quiet_hours_start" label="Starts" />
                  <input
                    id="setting-quiet_hours_start"
                    type="text"
                    value={settings.quiet_hours_start || "22:00"}
                    onChange={(e) => patch("quiet_hours_start", e.target.value)}
                    placeholder="22:00"
                  />
                </div>
                <div className="field">
                  <FieldLabel htmlFor="setting-quiet_hours_end" label="Ends" />
                  <input
                    id="setting-quiet_hours_end"
                    type="text"
                    value={settings.quiet_hours_end || "07:00"}
                    onChange={(e) => patch("quiet_hours_end", e.target.value)}
                    placeholder="07:00"
                  />
                </div>
              </section>
            ) : null}

            {activeSection === "ingest" ? (
              <section className="settings-panel settings-ingest" id="ingest" data-testid="settings-ingest" aria-labelledby="settings-ingest-heading">
                <p className="kicker" id="settings-ingest-heading">
                  Watch folder
                </p>
                <h2>Automatic ingest</h2>
                <p className="lede">
                  {WATCH_FOLDER_LEDE} To add a dump already on disk, use{" "}
                  <Link to="/maintain">Maintain</Link>.
                </p>
                <div className="field">
                  <FieldLabel htmlFor="setting-watch_root" label="Watch folder" help={FIELD_HELP.watch_root} />
                  <input
                    id="setting-watch_root"
                    type="text"
                    value={settings.watch_root || ""}
                    onChange={(e) => patch("watch_root", e.target.value)}
                    spellCheck={false}
                  />
                </div>
                <div className="field field-check">
                  <label htmlFor="setting-watch_enabled">
                    <input
                      id="setting-watch_enabled"
                      type="checkbox"
                      checked={Boolean(settings.watch_enabled)}
                      onChange={(e) => patch("watch_enabled", e.target.checked)}
                    />
                    Watch this folder
                  </label>
                </div>
              </section>
            ) : null}

            {activeSection === "about" ? <AboutPanel /> : null}

            {activeSection !== "appearance" && activeSection !== "about" ? (
              <div className="cta-row settings-save-row">
                <button type="submit" className="cta" data-testid="settings-save">
                  Save
                </button>
                <Link className="cta ghost" to="/maintain">
                  Open Maintain
                </Link>
              </div>
            ) : null}
          </form>
        </div>
      </div>
    </div>
  );
}
