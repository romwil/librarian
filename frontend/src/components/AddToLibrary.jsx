import { useEffect, useState } from "react";
import { api } from "../api.js";
import { ADD_TO_LIBRARY_LEDE, FIELD_HELP, humanError } from "../copy.js";
import { FieldLabel } from "./FieldHelp.jsx";
import { filterBrowseEntries } from "../ingest.js";

export default function AddToLibrary({ compact = false } = {}) {
  const [path, setPath] = useState("");
  const [root, setRoot] = useState("");
  const [parent, setParent] = useState(null);
  const [entries, setEntries] = useState([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  function load(next = path) {
    setError("");
    return api
      .fs(next)
      .then((data) => {
        setRoot(data.root || "");
        setPath(data.path || "");
        setParent(data.parent || null);
        setEntries(filterBrowseEntries(data.entries || []));
      })
      .catch((err) => setError(humanError(err)));
  }

  useEffect(() => {
    load("");
  }, []);

  async function onAdd() {
    if (!path) return;
    setBusy(true);
    setStatus("");
    setError("");
    try {
      const data = await api.ingest(path);
      const job = data.job || {};
      const word =
        job.status === "organized"
          ? "Arrived"
          : job.status === "review"
            ? "Needs you"
            : job.status === "failed"
              ? "Failed"
              : "On the way";
      setStatus(`${word} — ${job.title || path}`);
      await load(parent || root || "");
    } catch (err) {
      setError(humanError(err));
    } finally {
      setBusy(false);
    }
  }

  const heading = compact ? (
    <summary className="kicker">Add a volume already on disk</summary>
  ) : (
    <>
      <p className="kicker">Already on disk</p>
      <h2>Add to the shelves</h2>
    </>
  );

  const body = (
    <>
      <p className="lede">{ADD_TO_LIBRARY_LEDE}</p>
      {error ? <p className="alert">{error}</p> : null}
      {status ? <p className="muted">{status}</p> : null}
      <div className="field">
        <FieldLabel htmlFor={compact ? "hall-ingest-path" : "ingest-path"} label="Path" help={FIELD_HELP.ingest_path} />
        <input
          id={compact ? "hall-ingest-path" : "ingest-path"}
          value={path}
          onChange={(event) => setPath(event.target.value)}
          spellCheck={false}
        />
      </div>
      <ul className="fs-browser" aria-label="Folders under /data">
        {parent ? (
          <li>
            <button type="button" className="fs-row" onClick={() => load(parent)}>
              <span className="muted">↑</span> Up
            </button>
          </li>
        ) : null}
        {entries.map((entry) => (
          <li key={entry.path}>
            <button
              type="button"
              className={`fs-row${entry.path === path ? " is-on" : ""}`}
              onClick={() => (entry.kind === "dir" ? load(entry.path) : setPath(entry.path))}
            >
              <span className="muted">{entry.kind === "dir" ? "folder" : "file"}</span>
              {entry.name}
            </button>
          </li>
        ))}
      </ul>
      <div className="cta-row">
        <button type="button" className="cta" disabled={busy || !path} onClick={onAdd}>
          {busy ? "Adding…" : "Add"}
        </button>
      </div>
    </>
  );

  if (compact) {
    return (
      <details className="more-settings hall-ingest">
        {heading}
        {body}
      </details>
    );
  }

  return <section className="more-settings">{heading}{body}</section>;
}
