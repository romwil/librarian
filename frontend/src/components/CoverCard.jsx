import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { bookAvailability, catalogStatus } from "../availability.js";
import { saveBeyondGet } from "../beyondGet.js";
import AvailabilityActions from "./AvailabilityActions.jsx";
import CatalogVerb from "./CatalogVerb.jsx";
import {
  clothFor,
  coverAltText,
  coverCaption,
  coverClassNames,
  coverOverlay,
  coverTip,
  isBeyondWork,
  jobChipLabel,
  jobChipTone,
  localCoverUrl,
  shouldOpenPeek,
} from "../cover.js";
import { canPromoteIncomingMusic, humanError } from "../copy.js";
import { beyondHostName, findHref, gapFindFields } from "../find.js";
import { isIncompleteOwnedPartSet, partSetFindFields } from "../findParts.js";
import { canListenInApp, workListenPath } from "../listen.js";
import { canOpenInlineMedia, canReadInApp, readerCtaLabel, workDownloadUrl, workReaderPath } from "../reader.js";
import StacksCardFooter from "./StacksCardFooter.jsx";
import WorkActionMenu from "./WorkActionMenu.jsx";
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

export default function CoverCard({ work, onRequest, badge, beyond = false, role = "reader", cardMode = "" }) {
  const peek = useWorkPeek();
  const navigate = useNavigate();
  const kind = work.kind || "book";
  const isGap = Boolean(work.gap || work.kind === "gap");
  const isBeyond = beyond || isBeyondWork(work);
  // The grip is the cover's only new control. Gap/beyond cards aren't real
  // catalog rows yet — no GET /api/works/:id to lazy-load, no menu to show.
  const showActions = Boolean(work.id) && !isGap && !isBeyond;
  const status = work.job_status || badge;
  const tone = isGap ? "" : jobChipTone(status);
  const chip = isGap ? "" : status ? jobChipLabel(status, role) : "";
  const art = localCoverUrl(work);
  const [artFailed, setArtFailed] = useState(false);
  const hasArt = Boolean(art) && !artFailed;
  const item = beyond ? { ...work, beyond: true } : work;
  const overlay = coverOverlay(item);
  const caption = coverCaption(item);
  const tip = coverTip(item);
  // Stacks names the title and the author. Hall and Search keep their verbs.
  const stacksCard = cardMode === "stacks";
  const host = beyond ? beyondHostName(work) : "";
  const beads = isGap ? gapBeadModel(work) : [];
  const [wantedRow, setWantedRow] = useState(null);
  const [queuedStatus, setQueuedStatus] = useState("");
  const [availabilityBusy, setAvailabilityBusy] = useState(false);
  const [getError, setGetError] = useState("");
  const availability = bookAvailability({
    work: { ...work, wanted: wantedRow || work.wanted },
    role,
    beyond,
  });
  const catalog = catalogStatus({
    work: {
      ...work,
      wanted: wantedRow || work.wanted,
      job_status: queuedStatus || status,
    },
    role,
    beyond,
  });
  const wantBody = availability.addBody || catalog.addBody;
  const alreadyQueued = catalog.verb === "Queued" || Boolean(queuedStatus);

  async function addWanted() {
    if (!wantBody || availabilityBusy) return;
    setAvailabilityBusy(true);
    setGetError("");
    try {
      const result = await api.addWanted(wantBody);
      if (result?.item) setWantedRow(result.item);
    } catch (err) {
      setGetError(humanError(err));
    } finally {
      setAvailabilityBusy(false);
    }
  }

  async function getBeyond() {
    if (!beyond || availabilityBusy || alreadyQueued) return;
    setAvailabilityBusy(true);
    setGetError("");
    try {
      const result = onRequest
        ? await onRequest({ ...work, beyond: true })
        : await saveBeyondGet(work);
      const wanted = result?.wanted || result?.item;
      if (wanted) setWantedRow(wanted);
      const nextStatus = result?.job?.status || result?.jobStatus || wanted?.status || "";
      if (nextStatus === "asked") setQueuedStatus("asked");
      else if (!wanted?.id) setQueuedStatus(nextStatus || "asked");
    } catch (err) {
      setGetError(humanError(err));
    } finally {
      setAvailabilityBusy(false);
    }
  }

  async function dismissWanted() {
    if (!availability.wantedId || availabilityBusy) return;
    setAvailabilityBusy(true);
    try {
      const result = await api.dismissWanted(availability.wantedId);
      if (result?.item) setWantedRow(result.item);
    } catch {
      /* keep the row visible so dismiss can be retried */
    } finally {
      setAvailabilityBusy(false);
    }
  }

  const [detail, setDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [favorite, setFavorite] = useState(Boolean(work.favorite));
  const [promoting, setPromoting] = useState(false);
  const [actionNote, setActionNote] = useState("");

  // Rail/browse summaries don't know Read/Listen/Download yet — the grip
  // lazy-loads the full work once, on first open.
  function loadDetail() {
    if (!showActions || detail || detailLoading) return;
    setDetailLoading(true);
    api
      .work(work.id)
      .then((data) => setDetail(data))
      .catch((err) => setActionNote(humanError(err)))
      .finally(() => setDetailLoading(false));
  }

  async function toggleFavorite() {
    try {
      const next = await api.favorite(work.id);
      setFavorite(Boolean(next.favorite));
    } catch (err) {
      setActionNote(humanError(err));
    }
  }

  async function promote() {
    if (!work.id || promoting) return;
    setPromoting(true);
    setActionNote("");
    try {
      const result = await api.promote(work.id);
      setDetail((current) => ({
        ...(current || {}),
        work: { ...(current?.work || {}), ...(result?.work || {}) },
      }));
    } catch (err) {
      setActionNote(humanError(err));
    } finally {
      setPromoting(false);
    }
  }

  const menuWork = detail?.work ? { ...work, ...detail.work } : work;
  const canDownload = Boolean(detail?.can_download);
  const canRead = Boolean(detail?.can_read) && canReadInApp(menuWork, detail?.files);
  const canListen = Boolean(detail?.listen?.can_listen) && canListenInApp(menuWork, detail?.files, canDownload);
  const canInlineOpen = canOpenInlineMedia(menuWork, canDownload, canRead);
  const readLabel = readerCtaLabel(menuWork) || "Read";
  const incompleteParts = isIncompleteOwnedPartSet(menuWork.part_set);
  const findMissingHref = incompleteParts ? findHref(partSetFindFields(menuWork)) : "";
  const canPromote = canPromoteIncomingMusic(menuWork, role);
  const playerLink = detail?.listen?.player || null;
  const komgaLink = detail?.komga?.reader || null;

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
      <div className="cover-frame">
      <button
        type="button"
        className={coverClassNames(item, { art: hasArt })}
        style={{ "--cloth": work.cloth || clothFor(tip || work.title), "--progress": `${work.progress || 0}%` }}
        onClick={onClick}
        title={tip || undefined}
        aria-label={hasArt && !isGap ? undefined : isGap ? `Find ${caption} beyond the shelves` : tip || caption}
      >
        <span className="cover-meta" aria-hidden="true">
          <strong>{overlay.title}</strong>
          <em>{overlay.byline}</em>
        </span>
        {overlay.chip ? (
          <span className="cover-chip" aria-hidden="true">
            {overlay.chip}
          </span>
        ) : null}
        {kind === "audiobook" ? <span className="cover-wave" aria-hidden="true" /> : null}
        {hasArt ? <img src={art} alt={coverAltText(work)} onError={() => setArtFailed(true)} /> : null}
        {chip ? (
          <span className={`live-chip${tone ? ` ${tone}` : ""}`} aria-hidden="true">
            {chip}
          </span>
        ) : null}
      </button>
        {showActions ? (
          <WorkActionMenu label={tip || caption} onOpen={loadDetail} testId="rail-action">
            <button type="button" className="work-action-item" onClick={toggleFavorite}>
              {favorite ? "In Favorites" : "Favorite"}
            </button>
            {detailLoading ? <span className="work-action-label">Warming the lamp…</span> : null}
            {detail && canListen ? (
              <Link className="work-action-item" to={workListenPath(work.id)}>
                {Number(menuWork.progress) > 0 ? "Continue listening" : "Listen"}
              </Link>
            ) : null}
            {detail && canRead ? (
              <Link className="work-action-item" to={workReaderPath(work.id)}>
                {readLabel}
              </Link>
            ) : detail && canInlineOpen ? (
              <a
                className="work-action-item"
                href={`/api/works/${encodeURIComponent(work.id)}/download?inline=1`}
                target="_blank"
                rel="noreferrer"
              >
                {readLabel}
              </a>
            ) : null}
            {detail && canListen && playerLink?.href ? (
              <a className="work-action-item" href={playerLink.href} target="_blank" rel="noreferrer">
                {playerLink.label || "Open in player"}
              </a>
            ) : null}
            {detail && komgaLink?.href ? (
              <a className="work-action-item" href={komgaLink.href} target="_blank" rel="noreferrer">
                {komgaLink.label || "Open in Komga"}
              </a>
            ) : null}
            {detail && canDownload ? (
              <a className="work-action-item" href={workDownloadUrl(work.id)}>
                Download
              </a>
            ) : null}
            {detail && canPromote ? (
              <button type="button" className="work-action-item" onClick={promote} disabled={promoting}>
                {promoting ? "Promoting…" : "Promote to Plexamp"}
              </button>
            ) : null}
            {detail && incompleteParts ? (
              <Link className="work-action-item" to={findMissingHref}>
                Find missing parts
              </Link>
            ) : null}
            <Link className="work-action-item" to={`/works/${encodeURIComponent(work.id)}`}>
              Open full page
            </Link>
            {actionNote ? (
              <p className="work-action-label" role="status">
                {actionNote}
              </p>
            ) : null}
          </WorkActionMenu>
        ) : null}
      </div>
      {stacksCard ? (
        <StacksCardFooter work={item} tip={tip} />
      ) : (
        <p className="cover-caption" title={tip || undefined}>
          {caption}
          {host ? <span className="cover-host"> · {host}</span> : null}
        </p>
      )}
      {beads.length ? (
        <div
          className="gap-beads"
          role="list"
          aria-label={work.gap_type === "multipart" ? "Multipart progress" : "Series progress"}
          data-testid="gap-beads"
        >
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
      {stacksCard ? (
        availability.verb === "want" ? (
          <>
            <AvailabilityActions
              view={availability}
              shelfVerbs={false}
              busy={availabilityBusy}
              onAdd={addWanted}
              onDismiss={dismissWanted}
            />
            {getError ? (
              <p className="catalog-status-error" role="alert">
                {getError}
              </p>
            ) : null}
          </>
        ) : null
      ) : availability.show ? (
        <>
          <AvailabilityActions
            view={availability}
            shelfVerbs
            busy={availabilityBusy}
            onAdd={addWanted}
            onDismiss={dismissWanted}
          />
          {getError ? (
            <p className="catalog-status-error" role="alert">
              {getError}
            </p>
          ) : null}
        </>
      ) : (
        <CatalogVerb
          view={catalog}
          busy={availabilityBusy}
          error={getError}
          onAdd={beyond ? getBeyond : addWanted}
        />
      )}
    </div>
  );
}
