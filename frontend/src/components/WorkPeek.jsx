import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { browseHref } from "../browse.js";
import {
  clothFor,
  coverClassNames,
  coverDisplayTitle,
  coverOverlay,
  coverWashStyle,
  coverWashUrl,
  formatPubAge,
  formatSize,
  isBeyondWork,
  isInboundJob,
  jobChipLabel,
  partHint,
} from "../cover.js";
import { canPromoteIncomingMusic, humanError, peekMediaNote } from "../copy.js";
import { looksLikeHtml, sanitizeDescriptionHtml } from "../description.js";
import { beyondHostName } from "../find.js";
import { canOpenInlineMedia, canReadInApp, workReaderPath } from "../reader.js";

export default function WorkPeek({ work, onClose, onRequest }) {
  const panel = useRef(null);
  const closeBtn = useRef(null);
  const [role, setRole] = useState("reader");
  const [jobStatus, setJobStatus] = useState(work?.job_status || "");
  const [error, setError] = useState("");
  const [artFailed, setArtFailed] = useState(false);
  const [detail, setDetail] = useState(null);
  const [promoting, setPromoting] = useState(false);

  useEffect(() => {
    setJobStatus(work?.job_status || "");
    setError("");
    setArtFailed(false);
    setDetail(null);
    setPromoting(false);
    if (!work?.id) return undefined;
    let alive = true;
    api
      .work(work.id)
      .then((data) => {
        if (!alive) return;
        setDetail(data);
      })
      .catch((err) => {
        if (!alive) return;
        setError(humanError(err));
      });
    return () => {
      alive = false;
    };
  }, [work]);

  useEffect(() => {
    if (!work) return undefined;
    api
      .me()
      .then((data) => setRole(data.user?.role || "reader"))
      .catch(() => {});
    function onKey(event) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    closeBtn.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [work, onClose]);

  if (!work) return null;

  const catalog = { ...work, ...(detail?.work || {}) };
  const href = catalog.id ? `/works/${catalog.id}` : null;
  const kind = catalog.kind || "work";
  const beyond = isBeyondWork(catalog);
  const displayTitle = coverDisplayTitle(catalog);
  const sizeLabel = formatSize(catalog.size);
  const ageLabel = formatPubAge(catalog.pub_date);
  const hostLabel = beyondHostName(catalog);
  const partLabel = partHint(catalog.title);
  const art = catalog.has_cover && catalog.id ? `/api/works/${catalog.id}/cover` : catalog.cover || "";
  const hasArt = Boolean(art) && !artFailed;
  const washUrl = !artFailed ? coverWashUrl(catalog) : "";
  const washStyle = washUrl ? coverWashStyle(catalog) : undefined;
  const overlay = coverOverlay(catalog);
  const detailMatches = Boolean(work?.id) && detail?.work?.id === work.id;
  const canDownload = Boolean(detailMatches && detail?.can_download);
  const canRead = Boolean(detailMatches && detail?.can_read && canReadInApp(catalog, detail?.files));
  const canInlineOpen = canOpenInlineMedia(catalog, canDownload, canRead);
  const fileCount = detailMatches ? detail?.file_count || 0 : 0;
  const mediaNote = peekMediaNote(catalog, {
    canDownload,
    ready: !work?.id || detailMatches || Boolean(error),
  });
  const openHref = catalog.id ? `/api/works/${catalog.id}/download?inline=1` : "";
  const downloadHref = catalog.id ? `/api/works/${catalog.id}/download` : "";
  const canPromote = canPromoteIncomingMusic(catalog, role);
  const descriptionHtml = looksLikeHtml(catalog.description)
    ? sanitizeDescriptionHtml(catalog.description)
    : "";

  async function favorite() {
    if (!catalog.id) return;
    try {
      await api.favorite(catalog.id);
    } catch (err) {
      setError(humanError(err));
    }
  }

  async function request() {
    // Hard rule: only Find / Discover / peek Request wired by the parent may enqueue.
    // Never fall back to api.requestItem — Search and bare peeks must not touch SAB.
    if (!onRequest) return;
    setError("");
    try {
      const result = await onRequest({
        title: catalog.title,
        guid: catalog.guid,
        kind: catalog.kind,
        download_url: catalog.download_url,
        author: catalog.author,
        isbn: catalog.isbn,
      });
      const status = result?.job?.status || (role === "reader" ? "asked" : "queued");
      setJobStatus(status);
    } catch (err) {
      setError(humanError(err));
    }
  }

  async function promote() {
    if (!catalog.id || promoting) return;
    setError("");
    setPromoting(true);
    try {
      const next = await api.promote(catalog.id);
      if (next?.work) {
        setDetail((current) => ({
          ...(current || {}),
          work: { ...(current?.work || catalog), ...next.work },
        }));
      } else {
        const refreshed = await api.work(catalog.id);
        setDetail(refreshed);
      }
    } catch (err) {
      setError(humanError(err));
    } finally {
      setPromoting(false);
    }
  }

  return (
    <>
      <button type="button" className="scrim" aria-label="Close peek" onClick={onClose} />
      <aside
        className={`peek${washUrl ? " has-wash" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-labelledby="peek-title"
        data-testid="peek"
        ref={panel}
        style={washStyle}
      >
        {washUrl ? <div className="peek-wash" aria-hidden="true" data-testid="peek-wash" /> : null}
        {washUrl ? <div className="peek-wash-scrim" aria-hidden="true" /> : null}
        <header className="peek-head">
          <p className="kicker">{kind}</p>
          <button type="button" className="peek-close" aria-label="Close" ref={closeBtn} onClick={onClose}>
            ×
          </button>
        </header>
        <div className="peek-body">
          <div className="peek-layout">
            <div
              className={coverClassNames(catalog, { art: hasArt })}
              style={{ "--cloth": catalog.cloth || clothFor(catalog.title) }}
              aria-hidden="true"
            >
              <span className="cover-meta">
                <strong>{overlay.title}</strong>
                <em>{overlay.byline}</em>
              </span>
              {overlay.chip ? <span className="cover-chip">{overlay.chip}</span> : null}
              {kind === "audiobook" ? <span className="cover-wave" aria-hidden="true" /> : null}
              {hasArt ? <img src={art} alt="" onError={() => setArtFailed(true)} /> : null}
            </div>
            <div className="peek-copy">
              <h1 id="peek-title" title={catalog.title !== displayTitle ? catalog.title : undefined}>
                {displayTitle}
              </h1>
              <div className="chip-row peek-meta" data-testid="peek-meta">
                {kind ? <span className="chip is-on">{kind}</span> : null}
                {catalog.year ? <span className="chip">{catalog.year}</span> : null}
                {sizeLabel ? <span className="chip">{sizeLabel}</span> : null}
                {ageLabel ? <span className="chip">{ageLabel}</span> : null}
                {partLabel ? <span className="chip">Part {partLabel}</span> : null}
                {hostLabel ? <span className="chip">{hostLabel}</span> : null}
                {catalog.author ? (
                  <Link
                    className="chip"
                    to={browseHref({ author: catalog.author })}
                    onClick={(event) => {
                      if (event.metaKey || event.ctrlKey) return;
                      onClose();
                    }}
                    data-testid="peek-author-chip"
                  >
                    {catalog.author}
                  </Link>
                ) : null}
                {catalog.isbn ? <span className="chip font-mono">{catalog.isbn}</span> : null}
                {catalog.review_state === "needs_review" ? <span className="chip">Review</span> : null}
                {catalog.music_state === "incoming" ? <span className="chip">Incoming</span> : null}
                {isInboundJob(catalog.job_status) ? <span className="chip">On the way</span> : null}
                {fileCount > 1 ? <span className="chip">{fileCount} files</span> : null}
                {catalog.abs_item_id ? <span className="chip">On the player</span> : null}
              </div>
              {beyond && catalog.title && catalog.title !== displayTitle ? (
                <p className="peek-raw muted" data-testid="peek-raw-title">
                  {catalog.title}
                </p>
              ) : null}
              {catalog.description ? (
                descriptionHtml ? (
                  <div
                    className="blurb blurb-html"
                    data-testid="peek-description"
                    dangerouslySetInnerHTML={{ __html: descriptionHtml }}
                  />
                ) : (
                  <p className="blurb" data-testid="peek-description">
                    {catalog.description}
                  </p>
                )
              ) : null}
              {error ? <p className="alert">{error}</p> : null}
              {mediaNote ? (
                <p className="lede" data-testid="peek-media-note">
                  {mediaNote}
                </p>
              ) : null}
              <div className="cta-row compact peek-actions" data-testid="peek-actions">
                {href ? (
                  <>
                    {canRead ? (
                      <Link
                        className="cta compact"
                        to={workReaderPath(catalog.id)}
                        onClick={(event) => {
                          if (event.metaKey || event.ctrlKey) return;
                          onClose();
                        }}
                        data-testid="peek-open"
                      >
                        Open
                      </Link>
                    ) : canInlineOpen ? (
                      <a className="cta compact" href={openHref} target="_blank" rel="noreferrer" data-testid="peek-open">
                        Open
                      </a>
                    ) : null}
                    {canDownload ? (
                      <a className="cta outline compact" href={downloadHref} data-testid="peek-download">
                        Download
                      </a>
                    ) : null}
                    <button type="button" className="cta outline compact" onClick={favorite}>
                      Favorite
                    </button>
                    {canPromote ? (
                      <button
                        type="button"
                        className="cta ghost compact"
                        onClick={promote}
                        disabled={promoting}
                        aria-label="Promote to Plexamp"
                        data-testid="peek-promote"
                      >
                        Promote
                      </button>
                    ) : null}
                  </>
                ) : onRequest ? (
                  <button type="button" className="cta compact" onClick={request} disabled={Boolean(jobStatus)}>
                    {jobChipLabel(jobStatus, role)}
                  </button>
                ) : null}
              </div>
              {href ? (
                <p className="peek-full">
                  <Link
                    to={href}
                    onClick={(event) => {
                      if (event.metaKey || event.ctrlKey) return;
                      onClose();
                    }}
                  >
                    Open full page
                  </Link>
                  <span className="muted"> · same-tab dismisses peek · ⌘-click keeps peek</span>
                </p>
              ) : null}
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
