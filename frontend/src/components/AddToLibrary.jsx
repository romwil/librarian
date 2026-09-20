import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { ADD_TO_LIBRARY_LEDE, FIELD_HELP, humanError } from "../copy.js";
import {
  filterBrowseEntries,
  ingestIsRunning,
  ingestPhaseLabel,
  ingestProgressSummary,
  ingestResultMessage,
} from "../ingest.js";
import { FieldLabel } from "./FieldHelp.jsx";

export default function AddToLibrary({ compact = false, embedded = false } = {}) {
  const [path, setPath] = useState("");
  const [root, setRoot] = useState("");
  const [parent, setParent] = useState(null);
  const [entries, setEntries] = useState([]);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [progress, setProgress] = useState(null);
  const pollRef = useRef(0);
  const parentRef = useRef(parent);
  const rootRef = useRef(root);
  parentRef.current = parent;
  rootRef.current = root;

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

  useEffect(() => {
    let cancelled = false;
    api
      .ingestStatus()
      .then((data) => {
        if (cancelled) return;
        setProgress(data);
        if (ingestIsRunning(data)) {
          setBusy(true);
          setStatus(ingestProgressSummary(data) || "Adding…");
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!busy) return undefined;
    let cancelled = false;

    async function poll() {
      try {
        const data = await api.ingestStatus();
        if (cancelled) return;
        setProgress(data);
        const summary = ingestProgressSummary(data);
        if (summary) setStatus(summary);
        if (ingestIsRunning(data)) {
          pollRef.current = window.setTimeout(poll, 700);
          return;
        }
        setBusy(false);
        await load(parentRef.current || rootRef.current || "");
        if (data?.status === "failed") {
          setError(data.error || "Shelving failed.");
          setStatus("");
        } else if (data?.status === "completed") {
          setError("");
          setStatus(summary || "Finished looking.");
        }
      } catch (err) {
        if (cancelled) return;
        setBusy(false);
        setError(humanError(err));
      }
    }

    pollRef.current = window.setTimeout(poll, 400);
    return () => {
      cancelled = true;
      window.clearTimeout(pollRef.current);
    };
  }, [busy]);

  async function onAdd() {
    if (!path) return;
    setBusy(true);
    setStatus("Adding…");
    setError("");
    setProgress({
      status: "running",
      phase: "scanning",
      done: 0,
      total: 0,
      shelved: 0,
      review: 0,
      skipped: 0,
      current_title: "",
      current_path: path,
      logs: ["Starting…"],
    });
    try {
      const data = await api.ingest(path);
      setProgress(data);
      setStatus(ingestProgressSummary(data) || "Adding…");
      if (!ingestIsRunning(data) && data?.status === "completed") {
        setBusy(false);
        await load(parent || root || "");
        setStatus(ingestProgressSummary(data) || "Finished looking.");
      } else if (!ingestIsRunning(data) && data?.job) {
        // Legacy single-job shape (tests / older servers).
        const outcome = ingestResultMessage(data.job || {}, path);
        setBusy(false);
        await load(parent || root || "");
        if (outcome.kind === "error") {
          setError(outcome.text);
        } else {
          setStatus(outcome.text);
        }
      }
    } catch (err) {
      setBusy(false);
      setError(humanError(err));
      setStatus("");
    }
  }

  const heading = compact ? (
    <summary className="kicker">Add a volume already on disk</summary>
  ) : embedded ? null : (
    <>
      <p className="kicker">Already on disk</p>
      <h2>Add to the shelves</h2>
    </>
  );

  const showProgress =
    progress && (busy || progress.status === "completed" || progress.status === "failed");

  const body = (
    <>
      {embedded ? <p className="kicker">Already on disk</p> : null}
      <p className="lede">{ADD_TO_LIBRARY_LEDE}</p>
      {error ? <p className="alert">{error}</p> : null}
      {status && !showProgress ? <p className="muted">{status}</p> : null}
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
      {showProgress ? (
        <section className="ingest-progress" data-testid="ingest-progress" aria-live="polite">
          <p className="kicker">Shelving progress</p>
          <p className="muted">
            {ingestPhaseLabel(progress.phase)}
            {progress.total
              ? ` · ${progress.done || 0} of ${progress.total}`
              : progress.done
                ? ` · ${progress.done} done`
                : ""}
            {progress.shelved ? ` · shelved ${progress.shelved}` : ""}
            {progress.review ? ` · needs you ${progress.review}` : ""}
            {progress.skipped ? ` · skipped ${progress.skipped}` : ""}
          </p>
          {progress.current_title || progress.current_path ? (
            <p className="lede ingest-progress-title">{progress.current_title || progress.current_path}</p>
          ) : null}
          {status ? (
            <p className="muted" role="status">
              {status}
            </p>
          ) : null}
        </section>
      ) : null}
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

  if (embedded) {
    return <div className="settings-ingest-add">{body}</div>;
  }

  return <section className="more-settings">{heading}{body}</section>;
}
