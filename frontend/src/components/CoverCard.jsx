import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { clothFor, coverCaption, coverClassNames, coverOverlay, jobChipLabel, jobChipTone, shouldOpenPeek } from "../cover.js";
import { beyondHostName, findHref, gapFindFields } from "../find.js";
import { useWorkPeek } from "./WorkPeekProvider.jsx";

export default function CoverCard({ work, onRequest, badge, beyond = false, role = "reader" }) {
  const peek = useWorkPeek();
  const navigate = useNavigate();
  const kind = work.kind || "book";
  const title = work.title || "Untitled";
  const isGap = Boolean(work.gap || work.kind === "gap");
  const status = work.job_status || badge;
  const tone = isGap ? "" : jobChipTone(status);
  const chip = isGap ? "" : status ? jobChipLabel(status, role) : "";
  const art = work.has_cover && work.id ? `/api/works/${work.id}/cover` : work.cover || "";
  const [artFailed, setArtFailed] = useState(false);
  const hasArt = Boolean(art) && !artFailed;
  const overlay = coverOverlay(work);

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

  return (
    <div className={`cover-unit cover-unit-${kind}`}>
      <button
        type="button"
        className={coverClassNames(work, { art: hasArt })}
        style={{ "--cloth": work.cloth || clothFor(title), "--progress": `${work.progress || 0}%` }}
        onClick={onClick}
        aria-label={isGap ? `Find ${coverCaption(work)} beyond the shelves` : coverCaption(work)}
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
      <p className="cover-caption">
        {coverCaption(work)}
        {beyond && beyondHostName(work) ? <span className="cover-host"> · {beyondHostName(work)}</span> : null}
      </p>
    </div>
  );
}
