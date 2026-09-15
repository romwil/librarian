import { useState } from "react";
import { clothFor, coverCaption, coverClassNames, coverOverlay, jobChipLabel, shouldOpenPeek } from "../cover.js";
import { useWorkPeek } from "./WorkPeekProvider.jsx";

export default function CoverCard({ work, onRequest, badge, beyond = false, role = "reader" }) {
  const peek = useWorkPeek();
  const kind = work.kind || "book";
  const title = work.title || "Untitled";
  const status = work.job_status || badge;
  const chip = status ? jobChipLabel(status, role) : "";
  const art = work.has_cover && work.id ? `/api/works/${work.id}/cover` : work.cover || "";
  const [artFailed, setArtFailed] = useState(false);
  const hasArt = Boolean(art) && !artFailed;
  const overlay = coverOverlay(work);

  function onClick(event) {
    if (!shouldOpenPeek(event)) return;
    event.preventDefault();
    peek.openWork({ ...work, beyond, job_status: status }, { triggerEl: event.currentTarget, onRequest });
  }

  return (
    <div className={`cover-unit cover-unit-${kind}`}>
      <button
        type="button"
        className={coverClassNames(work, { art: hasArt })}
        style={{ "--cloth": work.cloth || clothFor(title), "--progress": `${work.progress || 0}%` }}
        onClick={onClick}
        aria-label={coverCaption(work)}
      >
        <span className="cover-meta">
          <strong>{overlay.title}</strong>
          <em>{overlay.byline}</em>
        </span>
        {overlay.chip ? <span className="cover-chip">{overlay.chip}</span> : null}
        {kind === "audiobook" ? <span className="cover-wave" aria-hidden="true" /> : null}
        {hasArt ? <img src={art} alt="" onError={() => setArtFailed(true)} /> : null}
        {chip ? (
          <span className={`live-chip${status === "asked" ? " is-asked" : ""}${status === "failed" ? " is-failed" : ""}`}>
            {chip}
          </span>
        ) : null}
      </button>
      <p className="cover-caption">{coverCaption(work)}</p>
    </div>
  );
}
