import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import WarmLoad from "../components/WarmLoad.jsx";
import { humanError } from "../copy.js";
import { notedFindHref, notedSearchHref, notedWantedBody } from "../noted.js";

const PERIODS = [
  ["daily", "Daily"],
  ["weekly", "Weekly"],
];

function itemKey(item, kind) {
  return `${item?.title || ""}|${item?.author || ""}|${item?.isbn || ""}|${kind}`;
}

export default function NotedPage() {
  const [period, setPeriod] = useState("daily");
  const [preset, setPreset] = useState("hardcover-fiction");
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [saved, setSaved] = useState({});
  const [busy, setBusy] = useState("");

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .noted({ period, preset })
      .then((data) => {
        if (!alive) return;
        setPayload(data);
        setError("");
        setLoading(false);
      })
      .catch((err) => {
        if (!alive) return;
        setError(humanError(err));
        setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [period, preset]);

  async function add(item, kind) {
    const key = itemKey(item, kind);
    setBusy(key);
    setError("");
    try {
      await api.addWanted(notedWantedBody(item, kind));
      setSaved((current) => ({ ...current, [key]: true }));
    } catch (err) {
      setError(humanError(err));
    } finally {
      setBusy("");
    }
  }

  const lanes = payload?.lanes || [];
  const presets =
    lanes.find((lane) => lane.id === "bestsellers")?.presets || [];

  return (
    <div className="admin-room page-settle" data-testid="noted-page">
      <p className="kicker">Beyond the shelves</p>
      <h1>New & noted</h1>
      <p className="lede">
        Trending books, bestseller lists, and what the indexers just posted. Search the shelves, find beyond, or add it to Wanted.
      </p>
      <div className="chip-row" data-testid="noted-periods">
        {PERIODS.map(([value, label]) => (
          <button
            key={value}
            type="button"
            className={value === period ? "chip is-current" : "chip"}
            onClick={() => setPeriod(value)}
            aria-pressed={value === period}
          >
            {label}
          </button>
        ))}
        {presets.length ? (
          <label className="chip">
            List
            <select
              value={preset}
              onChange={(event) => setPreset(event.target.value)}
              aria-label="Bestseller list"
              data-testid="noted-preset"
            >
              {presets.map((row) => (
                <option key={row.list_name_encoded} value={row.list_name_encoded}>
                  {row.display_name}
                </option>
              ))}
            </select>
          </label>
        ) : null}
      </div>
      {error ? <p className="alert">{error}</p> : null}
      {loading ? <WarmLoad message="Warming New & noted…" testId="noted-loading" /> : null}
      {!loading
        ? lanes.map((lane) => (
            <section key={lane.id} className="stack" data-testid={`noted-lane-${lane.id}`}>
              <h2>{lane.label || lane.id}</h2>
              {lane.empty_copy && !lane.items?.length ? (
                <p className="empty-note" data-testid={`noted-empty-${lane.id}`}>
                  {lane.empty_copy}
                </p>
              ) : null}
              <ul className="stack">
                {(lane.items || []).map((item) => (
                  <li
                    key={`${lane.id}|${item.open_library_key || ""}|${item.category || ""}|${item.kind}|${item.title}|${item.author}|${item.rank || ""}`}
                    className="card"
                    data-testid="noted-item"
                    data-kind={item.kind || ""}
                    data-source={item.source || ""}
                  >
                    <strong>{item.title}</strong>
                    {item.author ? <p className="muted">{item.author}</p> : null}
                    <p className="chip-row">
                      <span className="chip">{item.kind === "audiobook" ? "Audiobook" : "Book"}</span>
                    </p>
                    {item.companion_note ? (
                      <p className="muted" data-testid="noted-companion">
                        {item.companion_note}
                      </p>
                    ) : null}
                    <div className="cta-row">
                      <Link className="cta outline compact" to={notedSearchHref(item)} data-testid="noted-search">
                        Search the shelves
                      </Link>
                      <Link className="cta outline compact" to={notedFindHref(item)} data-testid="noted-find">
                        Find beyond
                      </Link>
                      {payload?.can_add
                        ? ["book", "audiobook"].map((kind) => {
                            const key = itemKey(item, kind);
                            const done = Boolean(saved[key]);
                            return (
                              <button
                                key={kind}
                                type="button"
                                className="cta compact"
                                data-testid={`noted-want-${kind}`}
                                disabled={done || busy === key}
                                onClick={() => add(item, kind)}
                              >
                                {done ? "Wanted" : `Add to Wanted · ${kind}`}
                              </button>
                            );
                          })
                        : null}
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          ))
        : null}
    </div>
  );
}
