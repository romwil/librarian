import { useEffect, useState } from "react";
import { api } from "../api.js";
import { FieldLabel } from "./FieldHelp.jsx";
import { FIELD_HELP, humanError } from "../copy.js";
import { KINDS } from "../find.js";

const RSS_KINDS = KINDS.filter(([value]) => value);

export default function RssPanel({ compact = false }) {
  const [feeds, setFeeds] = useState([]);
  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [kind, setKind] = useState("book");
  const [error, setError] = useState("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);

  function load() {
    return api
      .rssFeeds()
      .then((data) => setFeeds(data.feeds || []))
      .catch((err) => setError(humanError(err)));
  }

  useEffect(() => {
    load();
  }, []);

  async function addFeed(event) {
    event.preventDefault();
    setError("");
    setNote("");
    setBusy(true);
    try {
      await api.saveRss({ name, url, kind, enabled: true });
      setName("");
      setUrl("");
      setKind("book");
      await load();
      setNote("Subscribed. New items wait as Asked on Queue.");
    } catch (err) {
      setError(humanError(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className={compact ? "rss-panel is-compact" : "rss-panel"}>
      {compact ? <p className="kicker">RSS</p> : null}
      <p className="lede">
        Subscribe to a Newznab RSS for one kind. New items become Asked slips — confirm on Queue before the
        downloader runs. TV and movies are refused.
      </p>
      {error ? <p className="alert">{error}</p> : null}
      {note ? <p className="muted">{note}</p> : null}
      <ul className="stack rss-list">
        {feeds.map((feed) => (
          <li key={feed.id} className="rss-row">
            <div>
              <strong>{feed.name}</strong>
              <p className="muted">
                {feed.kind}
                {feed.enabled ? "" : " · paused"}
                {feed.last_error ? ` · ${feed.last_error}` : ""}
              </p>
            </div>
            <button
              type="button"
              className="cta ghost compact"
              onClick={async () => {
                setError("");
                try {
                  await api.deleteRss(feed.id);
                  await load();
                } catch (err) {
                  setError(humanError(err));
                }
              }}
            >
              Remove
            </button>
          </li>
        ))}
      </ul>
      <form className="rss-add" onSubmit={addFeed}>
        <div className="field">
          <FieldLabel htmlFor="rss-name" label="Feed name" />
          <input id="rss-name" value={name} onChange={(event) => setName(event.target.value)} />
        </div>
        <div className="field">
          <FieldLabel htmlFor="rss-url" label="RSS URL" help={FIELD_HELP.rss_url} />
          <input
            id="rss-url"
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            required
            spellCheck={false}
          />
        </div>
        <div className="field">
          <FieldLabel htmlFor="rss-kind" label="Kind" help={FIELD_HELP.rss_kind} />
          <select id="rss-kind" value={kind} onChange={(event) => setKind(event.target.value)}>
            {RSS_KINDS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="cta-row">
          <button type="submit" className="cta outline" disabled={busy || !url.trim()}>
            {busy ? "Saving…" : "Subscribe"}
          </button>
        </div>
      </form>
    </div>
  );
}
