import { useEffect, useMemo, useState } from "react";
import { beyondHostName } from "../find.js";
import {
  defaultPartSelectionKeys,
  finishThisSetAction,
  formatBytes,
  partBeadStates,
  partSetRequestAction,
  partSetStatusLine,
} from "../findParts.js";
import { jobChipLabel, jobChipTone } from "../cover.js";
import { humanError } from "../copy.js";
import { useWorkPeek } from "./WorkPeekProvider.jsx";
import { api } from "../api.js";

function itemKey(item) {
  return item?.guid || item?.title || "";
}

export default function PartSetCard({
  set,
  onRequest,
  role = "reader",
  jobs = {},
  chase = null,
}) {
  const peek = useWorkPeek();
  const [selected, setSelected] = useState(() => new Set(defaultPartSelectionKeys(set)));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [progress, setProgress] = useState("");
  const [etaMinutes, setEtaMinutes] = useState(null);
  const [etaApproximate, setEtaApproximate] = useState(false);
  const [collapsed, setCollapsed] = useState(false);

  const enriched = useMemo(
    () => ({
      ...set,
      chaseQueriesTried: chase?.queriesTried ?? set.chaseQueriesTried ?? 0,
    }),
    [set, chase],
  );
  const status = partSetStatusLine(enriched);
  const beads = useMemo(() => partBeadStates(enriched), [enriched]);
  const finish = useMemo(
    () => finishThisSetAction(enriched, { etaMinutes, approximate: etaApproximate }),
    [enriched, etaMinutes, etaApproximate],
  );
  const selectable = useMemo(() => {
    const listed = enriched.parts.map((row) => row.item);
    const gaps = enriched.missingItems || [];
    const byKey = new Map();
    for (const item of [...gaps, ...listed]) {
      const key = itemKey(item);
      if (key) byKey.set(key, item);
    }
    return [...byKey.values()];
  }, [enriched]);
  const selectedItems = selectable.filter((item) => selected.has(itemKey(item)));
  const action = partSetRequestAction(enriched, selectedItems.length);
  const requestClass = action.style === "primary" ? "cta compact" : "cta compact outline";
  const chasing = chase?.status === "searching";
  const chaseLive =
    chasing
      ? `Searching for missing parts… (${chase.queriesTried || 0}${chase.total ? ` of ${chase.total}` : ""})`
      : chase?.status === "done" && chase.queriesTried
        ? `Searched ${chase.queriesTried} quer${chase.queriesTried === 1 ? "y" : "ies"} for missing parts.`
        : "";
  const showFinish = Boolean(finish) && (chase?.status === "done" || (enriched.missingItems || []).length > 0);

  useEffect(() => {
    setSelected(new Set(defaultPartSelectionKeys(set)));
  }, [set.id, set.found, set.missingItems?.length, set.complete]);

  useEffect(() => {
    if (!showFinish) {
      setCollapsed(false);
      return undefined;
    }
    setCollapsed(true);
    let alive = true;
    const gaps = enriched.missingItems || [];
    const totalBytes = gaps.reduce((sum, item) => {
      const n = Number(item?.size);
      return Number.isFinite(n) && n > 0 ? sum + n : sum;
    }, 0);
    api
      .finishEta({
        missingCount: gaps.length,
        kind: enriched.kind || "",
        totalBytes: totalBytes > 0 ? totalBytes : null,
        multipart: true,
      })
      .then((data) => {
        if (!alive) return;
        const minutes = Number(data?.eta_minutes);
        setEtaMinutes(Number.isFinite(minutes) && minutes > 0 ? minutes : null);
        setEtaApproximate(Boolean(data?.approximate) && Number.isFinite(minutes) && minutes > 0);
      })
      .catch(() => {
        if (!alive) return;
        setEtaMinutes(null);
        setEtaApproximate(false);
      });
    return () => {
      alive = false;
    };
  }, [showFinish, enriched.missingItems?.length, enriched.kind, set.id]);

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

  function onPartKeyDown(event, key) {
    if (event.key === " " || event.key === "Enter") {
      event.preventDefault();
      if (!busy && !jobs[key]) toggle(key);
    }
  }

  return (
    <article
      className={`part-set${chasing ? " is-chasing" : ""}${collapsed && showFinish ? " is-finish" : ""}`}
      data-testid="part-set"
      data-complete={enriched.complete ? "1" : "0"}
      data-chasing={chasing ? "1" : "0"}
      data-finish={collapsed && showFinish ? "1" : "0"}
    >
      <header className="part-set-head">
        <div>
          <p className="kicker">Multipart · {enriched.kind || "release"}</p>
          <h3 className="part-set-title">{enriched.title}</h3>
          <p className="part-set-meta">
            <span className={`chip${enriched.complete ? " is-on" : ""}`}>{status}</span>
            {beyondHostName(enriched) ? <span className="muted"> · {beyondHostName(enriched)}</span> : null}
            {!enriched.complete && enriched.total > enriched.found ? (
              <span className="muted"> · indexer only returned some parts</span>
            ) : null}
          </p>
          {beads.length > 0 && beads.length <= 48 ? (
            <div className="part-beads" role="img" aria-label={`${enriched.found} of ${enriched.total} parts found`} data-testid="part-beads">
              {beads.map((bead) => (
                <span
                  key={bead.part}
                  className={`part-bead is-${bead.state}${chasing && bead.state === "missing" ? " is-pulse" : ""}`}
                  title={`Part ${bead.part}`}
                />
              ))}
            </div>
          ) : null}
        </div>
        <div className="part-set-actions">
          {showFinish && finish ? (
            <button
              type="button"
              className="cta compact"
              disabled={busy || !finish.enabled}
              onClick={() => requestItems(finish.items)}
              data-testid="part-set-finish"
            >
              {busy ? progress || "Requesting…" : finish.label}
            </button>
          ) : null}
          {!collapsed || !showFinish ? (
            <>
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
            </>
          ) : (
            <button type="button" className="chip" onClick={() => setCollapsed(false)} data-testid="part-set-expand">
              Show parts
            </button>
          )}
        </div>
      </header>

      {chaseLive ? (
        <p className={`part-chase${chasing ? " is-shimmer" : ""}`} role="status" aria-live="polite" data-testid="part-chase-live">
          {chaseLive}
        </p>
      ) : null}

      {!collapsed || !showFinish ? (
        <div className="part-grid" role="list">
          {enriched.parts.map(({ part, item, alternatives }) => {
            const key = itemKey(item);
            const checked = selected.has(key);
            const job = jobs[key];
            const tone = jobChipTone(job);
            const chip = job ? jobChipLabel(job, role) : "";
            const size = formatBytes(item.size);
            return (
              <div
                key={key}
                className={`part-cell${checked ? " is-selected" : ""}`}
                role="listitem"
                tabIndex={0}
                onKeyDown={(event) => onPartKeyDown(event, key)}
                data-testid="part-cell"
              >
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
                  <span className="part-label">
                    Part {part}
                    {enriched.total ? ` / ${enriched.total}` : ""}
                  </span>
                  {size ? <span className="part-size">{size}</span> : null}
                  {alternatives?.length ? <span className="part-alts muted">+{alternatives.length} alt</span> : null}
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
      ) : null}

      {action.honesty && (!collapsed || !showFinish) ? (
        <p className="part-missing muted" data-testid="part-set-honesty">
          {action.honesty}
        </p>
      ) : null}
      {enriched.missing?.length && enriched.missing.length <= 12 && (!collapsed || !showFinish) ? (
        <p className="part-missing muted" data-testid="part-set-missing">
          Missing parts: {enriched.missing.join(", ")}
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
