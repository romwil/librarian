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
    <div className={`cover-unit cover-unit-${kind}${beyond ? " is-beyond" : ""}`}>
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
    </div>
  );
}
