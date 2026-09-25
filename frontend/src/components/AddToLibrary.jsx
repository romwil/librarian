import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { ADD_TO_LIBRARY_LEDE, FIELD_HELP, humanError } from "../copy.js";
import {
  filterBrowseEntries,
  ingestDisplayPath,
  ingestIsRunning,
  ingestLegacyJob,
  ingestPhaseLabel,
  ingestProgressPercent,
  ingestProgressSummary,
  ingestProgressTallies,
  ingestResultMessage,
  ingestTallyLines,
} from "../ingest.js";
import { FieldLabel } from "./FieldHelp.jsx";

export default function AddToLibrary({ embedded = false } = {}) {
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
    setStatus("Scanning…");
    setError("");
    setProgress({
      status: "running",
      phase: "scanning",
      done: 0,
      total: 0,
      shelved: 0,
      review: 0,
      skipped: 0,
      duplicates: 0,
      volumes_found: 0,
      files_found: 0,
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
      } else if (!ingestIsRunning(data)) {
        const legacy = ingestLegacyJob(data);
        if (legacy) {
          // Legacy single-job shape (tests / older servers).
          const outcome = ingestResultMessage(legacy, path);
          setBusy(false);
          await load(parent || root || "");
          if (outcome.kind === "error") {
            setError(outcome.text);
          } else {
            setStatus(outcome.text);
          }
        }
      }
    } catch (err) {
      setBusy(false);
      setError(humanError(err));
      setStatus("");
    }
  }

  const heading = embedded ? null : (
    <>
      <p className="kicker">Already on disk</p>
      <h2>Add to the shelves</h2>
    </>
  );

  const showProgress =
    !embedded &&
    progress &&
    (busy || progress.status === "completed" || progress.status === "failed");
  const percent = showProgress ? ingestProgressPercent(progress) : null;
  const tallies = showProgress ? ingestProgressTallies(progress) : null;
  const tallyLines = showProgress ? ingestTallyLines(progress) : [];
  const displayPath = showProgress
    ? ingestDisplayPath(progress.current_path || progress.source_path || "")
    : "";
  const recentLogs = showProgress && Array.isArray(progress.logs) ? progress.logs.slice(-6) : [];

  const progressPanel = showProgress ? (
    <section className="ingest-progress" data-testid="ingest-progress" aria-live="polite">
      <p className="kicker">Shelving progress</p>
      <p className="muted">
        {ingestPhaseLabel(progress.phase)}
        {progress.total
          ? ` · ${progress.done || 0} of ${progress.total}`
          : tallies?.volumes
            ? ` · found ${tallies.volumes} volumes`
            : progress.done
              ? ` · ${progress.done} done`
              : ""}
        {tallies?.files && progress.phase === "scanning" ? ` · ${tallies.files} files` : ""}
        {percent != null ? ` · ${percent}%` : ""}
      </p>
      {percent != null ? (
        <div
          className="ingest-progress-meter"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          aria-label="Shelving progress"
        >
          <span className="ingest-progress-meter-fill" style={{ width: `${percent}%` }} />
        </div>
      ) : progress.phase === "scanning" ? (
        <div className="ingest-progress-meter ingest-progress-meter--indeterminate" aria-hidden="true">
          <span className="ingest-progress-meter-fill" />
        </div>
      ) : null}
      {progress.current_title ? <p className="lede ingest-progress-title">{progress.current_title}</p> : null}
      {displayPath ? (
        <p className="muted ingest-progress-path" title={progress.current_path || progress.source_path || ""}>
          {displayPath}
        </p>
      ) : null}
      {tallyLines.length ? (
        <ul className="ingest-progress-tallies" data-testid="ingest-tallies">
          {tallyLines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : null}
      {status ? (
        <p className="muted" role="status">
          {status}
        </p>
      ) : null}
      {recentLogs.length ? (
        <details className="ingest-progress-log">
          <summary className="muted">Recent activity</summary>
          <ul>
            {recentLogs.map((line, index) => (
              <li key={`${index}-${line}`}>{line}</li>
            ))}
          </ul>
        </details>
      ) : null}
    </section>
  ) : null;

  const body = (
    <>
      {embedded ? <p className="kicker">Already on disk</p> : null}
      <p className="lede">{ADD_TO_LIBRARY_LEDE}</p>
      {error ? <p className="alert">{error}</p> : null}
      {status && !showProgress ? <p className="muted">{status}</p> : null}
      {progressPanel}
      <div className="field">
        <FieldLabel htmlFor="ingest-path" label="Path" help={FIELD_HELP.ingest_path} />
        <input
          id="ingest-path"
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

  if (embedded) {
    return <div className="settings-ingest-add">{body}</div>;
  }

  return <section className="more-settings">{heading}{body}</section>;
}
