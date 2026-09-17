import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  clothFor,
  coverCaption,
  coverClassNames,
  coverOverlay,
  coverTip,
  jobChipLabel,
  jobChipTone,
  shouldOpenPeek,
} from "../cover.js";
import { beyondHostName, findHref, gapFindFields } from "../find.js";
import { useWorkPeek } from "./WorkPeekProvider.jsx";

function gapBeadModel(work = {}) {
  const owned = [...new Set((work.owned_indexes || []).map(String).filter(Boolean))];
  const missing = [...new Set((work.series_missing || []).map(String).filter(Boolean))];
  const current = String(work.missing_index || work.series_index || "").trim();
  if (!owned.length && !missing.length) return [];
  const order = [];
  const seen = new Set();
  for (const value of [...owned, ...missing].sort((a, b) => {
    const na = Number(a);
    const nb = Number(b);
    if (Number.isFinite(na) && Number.isFinite(nb)) return na - nb;
    return String(a).localeCompare(String(b));
  })) {
    if (seen.has(value)) continue;
    seen.add(value);
    order.push(value);
  }
  if (order.length > 24) {
    const focus = current || missing[0] || owned[owned.length - 1];
    const idx = Math.max(0, order.indexOf(focus));
    const start = Math.max(0, idx - 8);
    return order.slice(start, start + 16).map((value) => ({
      value,
      state: owned.includes(value) ? "owned" : value === current ? "current" : "missing",
    }));
  }
  return order.map((value) => ({
    value,
    state: owned.includes(value) ? "owned" : value === current ? "current" : "missing",
  }));
}

export default function CoverCard({ work, onRequest, badge, beyond = false, role = "reader" }) {
  const peek = useWorkPeek();
  const navigate = useNavigate();
  const kind = work.kind || "book";
  const isGap = Boolean(work.gap || work.kind === "gap");
  const status = work.job_status || badge;
  const tone = isGap ? "" : jobChipTone(status);
  const chip = isGap ? "" : status ? jobChipLabel(status, role) : "";
  const art = work.has_cover && work.id ? `/api/works/${work.id}/cover` : work.cover || "";
  const [artFailed, setArtFailed] = useState(false);
  const hasArt = Boolean(art) && !artFailed;
  const item = beyond ? { ...work, beyond: true } : work;
  const overlay = coverOverlay(item);
  const caption = coverCaption(item);
  const tip = coverTip(item);
  const host = beyond ? beyondHostName(work) : "";
  const beads = isGap ? gapBeadModel(work) : [];

  function onClick(event) {
    if (isGap) {
      const href = findHref(gapFindFields(work));
      if (event.metaKey || event.ctrlKey) {
        window.open(href, "_blank", "noopener");
        return;
      }
      event.preventDefault();
      navigate(href);
      return;
    }
    if (!shouldOpenPeek(event)) return;
    event.preventDefault();
    peek.openWork({ ...work, beyond, job_status: status }, { triggerEl: event.currentTarget, onRequest });
  }

  function onBeadClick(event, bead) {
    event.preventDefault();
    event.stopPropagation();
    if (bead.state === "owned") return;
    const href = findHref(
      gapFindFields({
        ...work,
        missing_index: bead.value,
        series_index: bead.value,
      }),
    );
    navigate(href);
  }

  return (
    <div className={`cover-unit cover-unit-${kind}${beyond ? " is-beyond" : ""}${isGap ? " is-gap-unit" : ""}`}>
      <button
        type="button"
        className={coverClassNames(item, { art: hasArt })}
        style={{ "--cloth": work.cloth || clothFor(tip || work.title), "--progress": `${work.progress || 0}%` }}
        onClick={onClick}
        title={tip || undefined}
        aria-label={isGap ? `Find ${caption} beyond the shelves` : tip || caption}
      >
        <span className="cover-meta">
          <strong>{overlay.title}</strong>
          <em>{overlay.byline}</em>
        </span>
        {overlay.chip ? <span className="cover-chip">{overlay.chip}</span> : null}
        {kind === "audiobook" ? <span className="cover-wave" aria-hidden="true" /> : null}
        {hasArt ? <img src={art} alt="" onError={() => setArtFailed(true)} /> : null}
        {chip ? <span className={`live-chip${tone ? ` ${tone}` : ""}`}>{chip}</span> : null}
      </button>
      <p className="cover-caption" title={tip || undefined}>
        {caption}
        {host ? <span className="cover-host"> · {host}</span> : null}
      </p>
      {beads.length ? (
        <div className="gap-beads" role="list" aria-label="Series progress" data-testid="gap-beads">
          {beads.map((bead) => (
            <button
              key={bead.value}
              type="button"
              role="listitem"
              className={`gap-bead is-${bead.state}`}
              title={bead.state === "owned" ? `Owned ${bead.value}` : `Find ${bead.value}`}
              aria-label={bead.state === "owned" ? `Owned ${bead.value}` : `Find missing ${bead.value}`}
              disabled={bead.state === "owned"}
              onClick={(event) => onBeadClick(event, bead)}
            />
          ))}
        </div>
      ) : null}
    </div>
  );
}
