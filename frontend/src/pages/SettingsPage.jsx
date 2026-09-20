import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { busyLabel, enrichIsRunning, enrichPhaseLabel, enrichProgressSummary, scanIsRunning, scanPhaseLabel, scanProgressSummary } from "../actionBusy.js";
import { FieldLabel } from "../components/FieldHelp.jsx";
import SetupWizard from "../components/SetupWizard.jsx";
import AddToLibrary from "../components/AddToLibrary.jsx";
import RssPanel from "../components/RssPanel.jsx";
import ReleaseNotesPanel from "../components/ReleaseNotesPanel.jsx";
import { FIELD_HELP, WATCH_FOLDER_LEDE, humanError, setupComplete, setupStepComplete } from "../copy.js";
import { fetchReleaseNotes, normalizeReleaseNotes } from "../lib/releaseNotes.js";
import LlmSettingsPanel from "../components/LlmSettingsPanel.jsx";
import AppearancePrefsPanel from "../components/AppearancePrefsPanel.jsx";

const MORE_FIELDS = [
  ["audiobook_target", "Audiobook target"],
  ["hardcover_api_token", "Hardcover token", true],
  ["nyt_books_api_key", "NYT Books API key", true],
  ["comicvine_api_key", "Comic Vine key", true],
  ["komga_url", "Komga URL"],
  ["komga_api_key", "Komga API key", true],
  ["komga_library_id", "Komga library id"],
  ["audiobookshelf_url", "Audiobookshelf URL"],
  ["audiobookshelf_api_token", "Audiobookshelf token", true],
  ["household_name", "Household name"],
];

export default function SettingsPage() {
  const [settings, setSettings] = useState(null);
  const [saved, setSaved] = useState("");
  const [error, setError] = useState("");
  const [ping, setPing] = useState("");
  const [scan, setScan] = useState("");
  const [scanning, setScanning] = useState(false);
  const [scanStatus, setScanStatus] = useState(null);
  const scanPollRef = useRef(0);
  const [enrich, setEnrich] = useState("");
  const [enriching, setEnriching] = useState(false);
  const [enrichStatus, setEnrichStatus] = useState(null);
  const enrichPollRef = useRef(0);
  const [suggestNote, setSuggestNote] = useState("");
  const [suggesting, setSuggesting] = useState(false);
  const [goodreads, setGoodreads] = useState("");
  const [importing, setImporting] = useState(false);
  const [csvFile, setCsvFile] = useState(null);
  const [step, setStep] = useState(0);
  const [absMatch, setAbsMatch] = useState(null);
  const [absNote, setAbsNote] = useState("");
  const [matching, setMatching] = useState(false);
  const [releases, setReleases] = useState([]);
  const [notesError, setNotesError] = useState("");
  const [notesLoading, setNotesLoading] = useState(true);

  useEffect(() => {
    api
      .settings()
      .then((data) => {
        setSettings(data.settings);
        setAbsMatch(data.abs_match || null);
        const next = [0, 1, 2, 3].find((index) => !setupStepComplete(data.settings, index));
        setStep(next == null ? 0 : next);
      })
      .catch((err) => setError(humanError(err)));
  }, []);

  useEffect(() => {
    let cancelled = false;
    setNotesLoading(true);
    fetchReleaseNotes()
      .then((payload) => {
        if (cancelled) return;
        setReleases(normalizeReleaseNotes(payload));
        setNotesError("");
        setNotesLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setReleases([]);
        setNotesError("Could not load release notes.");
        setNotesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (notesLoading) return;
    if (typeof window === "undefined") return;
    if (window.location.hash !== "#release-notes") return;
    document.getElementById("release-notes")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [notesLoading, releases]);

  useEffect(() => {
    let cancelled = false;
    api
      .enrichStatus()
      .then((status) => {
        if (cancelled) return;
        setEnrichStatus(status);
        if (enrichIsRunning(status)) {
          setEnriching(true);
          setEnrich(enrichProgressSummary(status) || busyLabel("enrich"));
        }
      })
      .catch(() => {});
    api
      .scanStatus()
      .then((status) => {
        if (cancelled) return;
        setScanStatus(status);
        if (scanIsRunning(status)) {
          setScanning(true);
          setScan(scanProgressSummary(status) || busyLabel("scan"));
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!scanning) return undefined;
    let cancelled = false;

    async function poll() {
      try {
        const status = await api.scanStatus();
        if (cancelled) return;
        setScanStatus(status);
        const summary = scanProgressSummary(status);
        if (summary) setScan(summary);
        if (scanIsRunning(status)) {
          scanPollRef.current = window.setTimeout(poll, 700);
          return;
        }
        setScanning(false);
        if (status?.status === "failed") {
          setScan(status.error || "Scan failed.");
        } else if (status?.status === "completed") {
          setScan(summary || "Scan finished.");
        }
      } catch (err) {
        if (cancelled) return;
        setScanning(false);
        setScan(humanError(err));
      }
    }

    scanPollRef.current = window.setTimeout(poll, 400);
    return () => {
      cancelled = true;
      window.clearTimeout(scanPollRef.current);
    };
  }, [scanning]);

  useEffect(() => {
    if (!enriching) return undefined;
    let cancelled = false;

    async function poll() {
      try {
        const status = await api.enrichStatus();
        if (cancelled) return;
        setEnrichStatus(status);
        const summary = enrichProgressSummary(status);
        if (summary) setEnrich(summary);
        if (enrichIsRunning(status)) {
          enrichPollRef.current = window.setTimeout(poll, 700);
          return;
        }
        setEnriching(false);
        if (status?.status === "failed") {
          setEnrich(status.error || "Enrich failed.");
        } else if (status?.status === "completed") {
          setEnrich(summary || "Enrich finished.");
        }
      } catch (err) {
        if (cancelled) return;
        setEnriching(false);
        setEnrich(humanError(err));
      }
    }

    enrichPollRef.current = window.setTimeout(poll, 400);
    return () => {
      cancelled = true;
      window.clearTimeout(enrichPollRef.current);
    };
  }, [enriching]);

  function patch(key, value) {
    setSettings((prev) => ({ ...prev, [key]: value }));
  }

  async function startScanShelves() {
    setScan("");
    setScanning(true);
    setScanStatus({
      status: "running",
      phase: "starting",
      logs: ["Starting scan…"],
      done: 0,
      total: 0,
      created: 0,
      updated: 0,
      review: 0,
      errors: 0,
    });
    try {
      const started = await api.scanShelves();
      setScanStatus(started);
      setScan(scanProgressSummary(started) || busyLabel("scan"));
      if (!scanIsRunning(started) && started?.status === "completed") {
        setScanning(false);
        setScan(scanProgressSummary(started) || "Scan finished.");
      }
    } catch (err) {
      setScanning(false);
      setScan(humanError(err));
    }
  }

  async function startEnrichShelves() {
    setEnrich("");
    setEnriching(true);
    setEnrichStatus({
      status: "running",
      phase: "starting",
      logs: ["Starting enrich…"],
      done: 0,
      total: 0,
      updated: 0,
      skipped: 0,
      errors: 0,
    });
    try {
      const started = await api.enrichShelves();
      setEnrichStatus(started);
      setEnrich(enrichProgressSummary(started) || busyLabel("enrich"));
      if (!enrichIsRunning(started) && started?.status === "completed") {
        setEnriching(false);
        setEnrich(enrichProgressSummary(started) || "Enrich finished.");
      }
    } catch (err) {
      setEnriching(false);
      setEnrich(humanError(err));
    }
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
    <div className="admin-room settings-page">
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
      {suggestNote ? <p className={/^Suggestions /.test(suggestNote) ? "muted" : "alert"}>{suggestNote}</p> : null}
      {goodreads ? <p className={/^Imported /.test(goodreads) ? "muted" : "alert"}>{goodreads}</p> : null}
      <form className="settings-form" onSubmit={onSubmit}>
        <AppearancePrefsPanel />
        <SetupWizard settings={settings} onChange={patch} step={step} setStep={setStep} />
        <details className="more-settings">
          <summary className="kicker">Watch folder</summary>
          <p className="lede">{WATCH_FOLDER_LEDE}</p>
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
        </details>
        <details className="more-settings">
          <summary className="kicker">Quiet hours</summary>
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
        </details>
        <details className="more-settings">
          <summary className="kicker">Extra Newznab hosts</summary>
          <p className="lede">
            NZBFinder stays the first indexer. Add other Newznab v2 JSON hosts; Find merges hits and keeps going if one
            host fails.
          </p>
          {(settings.extra_indexers || []).map((row, index) => (
            <div key={row.id || index} className="extra-indexer">
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
              onClick={() =>
                patch("extra_indexers", [
                  ...(settings.extra_indexers || []),
                  { id: `extra-${Date.now()}`, name: "", url: "", api_token: "", enabled: true },
                ])
              }
            >
              Add indexer
            </button>
          </div>
        </details>
        <details className="more-settings">
          <summary className="kicker">Show categories</summary>
          <p className="lede">
            Off keeps Find on books, magazines, comics, audiobooks, and music. On, Discover can peruse every feed the
            indexer lists — including Movies, TV, and XXX. Those do not land on The Hall. Movies go to the downloader
            then Radarr; TV to Sonarr; XXX to the default download folder.
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
        </details>
        <details className="more-settings" open>
          <summary className="kicker">Language model — OpenAI, Anthropic, or Gemini</summary>
          <LlmSettingsPanel settings={settings} onChange={setSettings} />
        </details>
        <details className="more-settings">
          <summary className="kicker">More — listen target, Hardcover, NYT Books (optional), Comic Vine, household name</summary>
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
          <button
            type="button"
            className="cta outline"
            disabled={scanning}
            aria-busy={scanning || undefined}
            onClick={startScanShelves}
            data-testid="settings-scan"
          >
            {scanning ? busyLabel("scan") : "Scan the shelves"}
          </button>
          <button
            type="button"
            className="cta outline"
            disabled={enriching}
            aria-busy={enriching || undefined}
            onClick={startEnrichShelves}
            data-testid="settings-enrich"
          >
            {enriching ? busyLabel("enrich") : "Enrich the shelves"}
          </button>
          <button
            type="button"
            className="cta outline"
            disabled={suggesting}
            onClick={async () => {
              setSuggestNote("");
              setSuggesting(true);
              try {
                const data = await api.refreshSuggestCache(false);
                const counts = data.counts || {};
                const total = Object.values(counts).reduce((sum, n) => sum + Number(n || 0), 0);
                setSuggestNote(`Suggestions refreshed · ${total} labels from the shelves`);
              } catch (err) {
                setSuggestNote(humanError(err));
              } finally {
                setSuggesting(false);
              }
            }}
          >
            {suggesting ? "Refreshing…" : "Refresh suggestions from shelves"}
          </button>
        </div>
        {scanStatus && (scanning || scanStatus.status === "completed" || scanStatus.status === "failed") ? (
          <section className="shelf-progress" data-testid="scan-progress" aria-live="polite">
            <p className="kicker">Scan progress</p>
            <p className="muted">
              {scanPhaseLabel(scanStatus.phase)}
              {scanStatus.total
                ? ` · ${scanStatus.done || 0} of ${scanStatus.total}`
                : scanStatus.done
                  ? ` · ${scanStatus.done} done`
                  : ""}
              {scanStatus.created ? ` · ${scanStatus.created} new` : ""}
              {scanStatus.updated ? ` · ${scanStatus.updated} updated` : ""}
              {scanStatus.review ? ` · ${scanStatus.review} need review` : ""}
              {scanStatus.errors ? ` · ${scanStatus.errors} failed` : ""}
            </p>
            {scanStatus.current_title || scanStatus.current_path ? (
              <p className="lede shelf-progress-title">{scanStatus.current_title || scanStatus.current_path}</p>
            ) : null}
            {scan ? (
              <p className="muted" role="status">
                {scan}
              </p>
            ) : null}
          </section>
        ) : null}
        {enrichStatus && (enriching || enrichStatus.status === "completed" || enrichStatus.status === "failed") ? (
          <section className="shelf-progress" data-testid="enrich-progress" aria-live="polite">
            <p className="kicker">Enrich progress</p>
            <p className="muted">
              {enrichPhaseLabel(enrichStatus.phase)}
              {enrichStatus.total
                ? ` · ${enrichStatus.done || 0} of ${enrichStatus.total}`
                : enrichStatus.done
                  ? ` · ${enrichStatus.done} done`
                  : ""}
              {enrichStatus.updated ? ` · ${enrichStatus.updated} filled` : ""}
              {enrichStatus.skipped ? ` · ${enrichStatus.skipped} skipped` : ""}
              {enrichStatus.errors ? ` · ${enrichStatus.errors} failed` : ""}
            </p>
            {enrichStatus.current_title ? (
              <p className="lede shelf-progress-title">{enrichStatus.current_title}</p>
            ) : null}
            {enrich ? (
              <p className="muted" role="status">
                {enrich}
              </p>
            ) : null}
          </section>
        ) : null}
        <details className="more-settings">
          <summary className="kicker">Goodreads CSV</summary>
          <p className="lede">
            Export a shelf from Goodreads and match by ISBN onto Favorites. Rows without an ISBN are skipped. No
            Goodreads login.
          </p>
          <div className="field">
            <FieldLabel htmlFor="goodreads-csv" label="Shelf export" help={FIELD_HELP.goodreads_csv} />
            <input
              id="goodreads-csv"
              type="file"
              accept=".csv,text/csv"
              onChange={(event) => setCsvFile(event.target.files?.[0] || null)}
            />
          </div>
          <div className="cta-row">
            <button
              type="button"
              className="cta outline"
              disabled={importing || !csvFile}
              onClick={async () => {
                if (!csvFile) return;
                setGoodreads("");
                setImporting(true);
                try {
                  const data = await api.importGoodreads(csvFile);
                  setGoodreads(
                    `Imported ${data.rows} rows · ${data.matched} matched · ${data.created} new · ${data.favorited} favorited · ${data.skipped} skipped`,
                  );
                } catch (err) {
                  setGoodreads(humanError(err));
                } finally {
                  setImporting(false);
                }
              }}
            >
              {importing ? "Importing…" : "Import Goodreads CSV"}
            </button>
          </div>
        </details>
      </form>
      <details className="more-settings">
        <summary className="kicker">RSS subscriptions</summary>
        <RssPanel />
      </details>
      <AddToLibrary />
      <section
        className="more-settings settings-release-notes"
        id="release-notes"
        aria-labelledby="settings-release-notes-heading"
      >
        <p className="kicker" id="settings-release-notes-heading">
          Release notes
        </p>
        <p className="lede">Full history from CHANGELOG — newest first.</p>
        {notesError ? (
          <p className="alert" data-testid="settings-release-notes-error">
            {notesError}
          </p>
        ) : notesLoading ? (
          <p className="muted" data-testid="settings-release-notes-loading">
            Loading release notes…
          </p>
        ) : (
          <ReleaseNotesPanel
            releases={releases}
            showJumpLinks
            scrollable
            testId="settings-release-notes"
          />
        )}
      </section>
    </div>
  );
}
