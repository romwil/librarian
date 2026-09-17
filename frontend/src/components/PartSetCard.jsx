import { useMemo, useState } from "react";
import {
  defaultPartSelectionKeys,
  formatBytes,
  partSetRequestAction,
  partSetStatusLine,
} from "../findParts.js";
import { jobChipLabel, jobChipTone } from "../cover.js";
import { beyondHostName } from "../find.js";
import { humanError } from "../copy.js";
import { useWorkPeek } from "./WorkPeekProvider.jsx";

function itemKey(item) {
  return item?.guid || item?.title || "";
}

export default function PartSetCard({
  set,
  onRequest,
  role = "reader",
  jobs = {},
}) {
  const peek = useWorkPeek();
  const [selected, setSelected] = useState(() => new Set(defaultPartSelectionKeys(set)));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState("");

  const status = partSetStatusLine(set);
  const selectable = useMemo(() => set.parts.map((row) => row.item), [set.parts]);
  const selectedItems = selectable.filter((item) => selected.has(itemKey(item)));
  const action = partSetRequestAction(set, selectedItems.length);
  const requestClass =
    action.style === "primary" ? "cta compact" : "cta compact outline";

  function toggle(key) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  function selectAll() {
    setSelected(new Set(selectable.map(itemKey)));
  }

  function clearAll() {
    setSelected(new Set());
  }

  async function requestItems(items) {
    if (!onRequest || !items.length || busy) return;
    setBusy(true);
    setError("");
    setProgress("");
    let done = 0;
    try {
      for (const item of items) {
        done += 1;
        setProgress(`Requesting ${done} of ${items.length}…`);
        await onRequest(item);
      }
      setProgress(items.length === 1 ? "Asked" : `${items.length} slips filed`);
    } catch (err) {
      setError(humanError(err));
      setProgress("");
    } finally {
      setBusy(false);
    }
  }

  function openPeek(item, event) {
    event?.preventDefault?.();
    peek.openWork({ ...item, beyond: true, job_status: jobs[itemKey(item)] }, { triggerEl: event?.currentTarget, onRequest });
  }

  return (
    <article className="part-set" data-testid="part-set" data-complete={set.complete ? "1" : "0"}>
      <header className="part-set-head">
        <div>
          <p className="kicker">Multipart · {set.kind || "release"}</p>
          <h3 className="part-set-title">{set.title}</h3>
          <p className="part-set-meta">
            <span className={`chip${set.complete ? " is-on" : ""}`}>{status}</span>
            {beyondHostName(set) ? <span className="muted"> · {beyondHostName(set)}</span> : null}
            {!set.complete && set.total > set.found ? (
              <span className="muted"> · indexer only returned some parts</span>
            ) : null}
          </p>
        </div>
        <div className="part-set-actions">
          <button type="button" className="chip" onClick={selectAll} disabled={busy}>
            Select all
          </button>
          <button type="button" className="chip" onClick={clearAll} disabled={busy}>
            Clear
          </button>
          <button
            type="button"
            className={requestClass}
            disabled={busy || !action.enabled}
            onClick={() => requestItems(selectedItems)}
            data-testid="part-set-request"
            data-action-kind={action.kind}
          >
            {busy ? progress || "Requesting…" : action.label}
          </button>
        </div>
      </header>

      <div className="part-grid" role="list">
        {set.parts.map(({ part, item, alternatives }) => {
          const key = itemKey(item);
          const checked = selected.has(key);
          const job = jobs[key];
          const tone = jobChipTone(job);
          const chip = job ? jobChipLabel(job, role) : "";
          const size = formatBytes(item.size);
          return (
            <div key={key} className={`part-cell${checked ? " is-selected" : ""}`} role="listitem">
              <label className="part-check">
                <input
                  type="checkbox"
                  checked={checked}
                  disabled={busy || Boolean(job)}
                  onChange={() => toggle(key)}
                  aria-label={`Part ${part}`}
                />
                <span className="part-num">{String(part).padStart(2, "0")}</span>
              </label>
              <button type="button" className="part-open" onClick={(event) => openPeek(item, event)}>
                <span className="part-label">Part {part}{set.total ? ` / ${set.total}` : ""}</span>
                {size ? <span className="part-size">{size}</span> : null}
                {alternatives?.length ? (
                  <span className="part-alts muted">+{alternatives.length} alt</span>
                ) : null}
              </button>
              <button
                type="button"
                className="part-request chip"
                disabled={busy || Boolean(job)}
                onClick={() => requestItems([item])}
              >
                {chip || (role === "reader" ? "Ask" : "Request")}
              </button>
              {chip ? <span className={`live-chip part-job${tone ? ` ${tone}` : ""}`}>{chip}</span> : null}
            </div>
          );
        })}
      </div>

      {action.honesty ? (
        <p className="part-missing muted" data-testid="part-set-honesty">
          {action.honesty}
        </p>
      ) : null}
      {set.missing?.length && set.missing.length <= 12 ? (
        <p className="part-missing muted" data-testid="part-set-missing">
          Missing parts: {set.missing.join(", ")}
        </p>
      ) : null}
      {error ? (
        <p className="alert" role="status">
          {error}
        </p>
      ) : progress && !busy ? (
        <p className="lede" role="status">
          {progress}
        </p>
      ) : null}
    </article>
  );
}
