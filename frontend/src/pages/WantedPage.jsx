import { useEffect, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { api } from "../api.js";
import { humanError } from "../copy.js";
import { wantedDeskModel } from "../wantedDesk.js";
import WarmLoad from "../components/WarmLoad.jsx";

const KINDS = ["audiobook", "book", "magazine", "comic", "music"];

export default function WantedPage() {
  const { user } = useOutletContext() || {};
  const role = user?.role || "reader";
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [busyId, setBusyId] = useState("");
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState({ title: "", author: "", kind: "audiobook" });

  function load() {
    return api
      .wanted()
      .then((data) => setItems(data.items || []))
      .catch((err) => setError(humanError(err)));
  }

  useEffect(() => {
    let alive = true;
    setLoading(true);
    api
      .wanted()
      .then((data) => {
        if (alive) setItems(data.items || []);
      })
      .catch((err) => {
        if (alive) setError(humanError(err));
      })
      .finally(() => {
        if (alive) setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, []);

  const desk = wantedDeskModel({ items, role });

  async function dismiss(id) {
    if (!id || busyId) return;
    setBusyId(id);
    setError("");
    try {
      await api.dismissWanted(id);
      await load();
    } catch (err) {
      setError(humanError(err));
    } finally {
      setBusyId("");
    }
  }

  async function add(event) {
    event.preventDefault();
    if (adding) return;
    const title = draft.title.trim();
    if (!title) {
      setError("A title is required.");
      return;
    }
    setAdding(true);
    setError("");
    try {
      await api.addWanted({
        title,
        author: draft.author.trim(),
        kind: draft.kind || "audiobook",
      });
      setDraft({ title: "", author: "", kind: draft.kind || "audiobook" });
      await load();
    } catch (err) {
      setError(humanError(err));
    } finally {
      setAdding(false);
    }
  }

  return (
    <div className="wanted-page page-settle" data-testid="wanted-page">
      <section className="browse-hero">
        <p className="kicker">Stacks</p>
        <h1>Wanted</h1>
        <p className="lede">Titles the house does not have yet. Search the shelves, or find them beyond.</p>
      </section>
      {error ? <p className="alert hall-alert">{error}</p> : null}
      {loading ? (
        <WarmLoad message="Opening Wanted…" testId="wanted-loading" />
      ) : desk.empty ? (
        <p className="lede" data-testid="wanted-empty">
          Nothing is wanted right now.
        </p>
      ) : (
        <ul className="wanted-list" data-testid="wanted-list">
          {desk.rows.map((row) => (
            <li key={row.id || row.title} className="wanted-row" data-testid="wanted-row">
              <div className="wanted-copy">
                <p className="wanted-title">
                  {row.workId ? <Link to={`/works/${row.workId}`}>{row.title}</Link> : row.title}
                </p>
                <p className="muted">
                  {[row.author, row.kind, row.statusLabel].filter(Boolean).join(" · ")}
                </p>
              </div>
              <div className="cta-row compact">
                <Link className="cta outline compact" to={row.searchHref}>
                  Search the shelves
                </Link>
                <Link className="cta outline compact" to={row.findHref}>
                  Find beyond
                </Link>
                {row.canDismiss ? (
                  <button
                    type="button"
                    className="cta outline compact"
                    onClick={() => dismiss(row.id)}
                    disabled={busyId === row.id}
                    data-testid="wanted-dismiss"
                  >
                    Dismiss
                  </button>
                ) : null}
              </div>
            </li>
          ))}
        </ul>
      )}
      {desk.canAdd ? (
        <form className="wanted-add" onSubmit={add} data-testid="wanted-add">
          <h2>Add to Wanted</h2>
          <label className="field">
            <span>Title</span>
            <input
              value={draft.title}
              onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))}
              aria-label="Title"
            />
          </label>
          <label className="field">
            <span>Author</span>
            <input
              value={draft.author}
              onChange={(event) => setDraft((current) => ({ ...current, author: event.target.value }))}
              aria-label="Author"
            />
          </label>
          <label className="field">
            <span>Kind</span>
            <select
              value={draft.kind}
              onChange={(event) => setDraft((current) => ({ ...current, kind: event.target.value }))}
              aria-label="Kind"
            >
              {KINDS.map((kind) => (
                <option key={kind} value={kind}>
                  {kind}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" className="cta compact" disabled={adding} data-testid="wanted-add-submit">
            Add to Wanted
          </button>
        </form>
      ) : null}
    </div>
  );
}
