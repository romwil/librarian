import { useEffect, useState } from "react";
import { Link, useOutletContext, useParams } from "react-router-dom";
import { api } from "../api.js";
import { busyLabel } from "../actionBusy.js";
import { ThinkingButton } from "../components/Thinking.jsx";
import { browseHref } from "../browse.js";
import { coverWashStyle, coverWashUrl, isInboundJob } from "../cover.js";
import {
  FINISH_PRIVATE_LABEL,
  FINISH_TELL_LABEL,
  canPromoteIncomingMusic,
  humanError,
  peekMediaNote,
} from "../copy.js";
import { looksLikeHtml, sanitizeDescriptionHtml } from "../description.js";
import { findHref, gapFindFields } from "../find.js";
import { companionAudiobookView } from "../audiobookCompanion.js";
import { bookAvailability, catalogStatus } from "../availability.js";
import AvailabilityActions from "../components/AvailabilityActions.jsx";
import CatalogVerb from "../components/CatalogVerb.jsx";
import { isIncompleteOwnedPartSet, ownedPartSetStatusLine, partSetFindFields } from "../findParts.js";
import { useAlbumPlayer } from "../hooks/useAlbumPlayer.js";
import { useWorkRooms, workCanListen, workCanRead } from "../hooks/useWorkRooms.js";
import { finishRitualCopy, finishWhisperInvite, hallLampPeriod } from "../lib/lampRituals.js";
import { catchUpCtaLabel, catchUpInvitation, missingRibbonBeads } from "../lib/seriesCatchUp.js";
import { isAudioFile, primaryListeningFile } from "../listen.js";
import { canOpenInlineMedia, primaryReadingFile, readerCtaLabel, workDownloadUrl, workPrimaryVerb } from "../reader.js";
import Rail from "../components/Rail.jsx";
import WorkActionMenu from "../components/WorkActionMenu.jsx";
import { WorkListenShell, WorkReaderShell } from "../components/WorkRoomShells.jsx";
import PlexampToast from "../components/PlexampToast.jsx";
import WarmLoad from "../components/WarmLoad.jsx";

export default function WorkPage() {
  const { id } = useParams();
  const { user } = useOutletContext();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [fmt, setFmt] = useState("");
  const [enriching, setEnriching] = useState(false);
  const [enrichNote, setEnrichNote] = useState("");
  const [editing, setEditing] = useState(false);
  const [editDraft, setEditDraft] = useState(null);
  const [editSaving, setEditSaving] = useState(false);
  const [fixing, setFixing] = useState(false);
  const [matchCandidates, setMatchCandidates] = useState([]);
  const [matchLoading, setMatchLoading] = useState(false);
  const [matchApplying, setMatchApplying] = useState("");
  const [whisperBody, setWhisperBody] = useState("");
  const [whisperNote, setWhisperNote] = useState("");
  const [plexamp, setPlexamp] = useState(null);
  const [finishCeremony, setFinishCeremony] = useState(false);
  const [finishWhisper, setFinishWhisper] = useState("");
  const [finishSaving, setFinishSaving] = useState(false);
  const [finishRitual, setFinishRitual] = useState(false);
  const album = useAlbumPlayer({
    workId: id,
    files: data?.files || [],
    enabled: Boolean(data?.can_download && data?.work?.kind === "music"),
  });
  const rooms = useWorkRooms({ id, data, setData });
  const { openReader, openListen } = rooms;

  useEffect(() => {
    let alive = true;
    setData(null);
    setError("");
    api
      .work(id)
      .then((payload) => {
        if (!alive) return;
        setData(payload);
      })
      .catch((err) => {
        if (alive) setError(humanError(err));
      });
    return () => {
      alive = false;
    };
  }, [id]);

  if (error) {
    return (
      <div className="admin-room page-settle">
        <p className="alert">{error}</p>
      </div>
    );
  }
  if (!data) {
    return (
      <div className="admin-room page-settle work-page">
        <WarmLoad message="Warming the lamp on this volume…" testId="work-loading" />
      </div>
    );
  }

  const work = data.work;
  const canRead = workCanRead(data);
  const canListen = workCanListen(data);
  const canInlineOpen = canOpenInlineMedia(work, Boolean(data.can_download), canRead);
  const playerLink = data.listen?.player || null;
  const absListenHref =
    playerLink?.provider === "audiobookshelf" && playerLink?.href ? String(playerLink.href) : "";
  const playerNote = data.listen?.player_note || "";
  const komgaLink = data.komga?.reader || null;
  const mediaNote = peekMediaNote(work, { canDownload: Boolean(data.can_download), ready: true });
  const descriptionHtml = looksLikeHtml(work.description) ? sanitizeDescriptionHtml(work.description) : "";
  const washUrl = coverWashUrl(work);
  const washStyle = coverWashStyle(work);
  const incompleteParts = isIncompleteOwnedPartSet(work.part_set);
  const findMissingHref = incompleteParts ? findHref(partSetFindFields(work)) : "";
  const partStatus = incompleteParts ? ownedPartSetStatusLine(work.part_set) : "";
  const audiobookCta = companionAudiobookView(data.audiobook);
  const availability = bookAvailability({
    work,
    audiobook: data.audiobook,
    wanted: data.wanted,
    role: user?.role || "reader",
  });
  const status = catalogStatus({
    work,
    role: user?.role || "reader",
  });
  const readLabel = readerCtaLabel(work) || "Read";
  const verb = workPrimaryVerb({
    canListen,
    canRead: canRead || (canInlineOpen && Boolean(readerCtaLabel(work))),
    canPlay: Boolean(album.enabled) && !canListen && !canRead,
    canDownload: Boolean(data.can_download),
    canWant: Boolean(availability.canAdd) || Boolean(status.canAdd),
  });
  const bestRead = primaryReadingFile(data.files || []);
  const bestListen = primaryListeningFile(data.files || []);
  const primaryFile =
    bestRead ||
    bestListen ||
    (data.files || []).find((file) => file && file.on_disk !== false && (file.filename || file.path)) ||
    null;
  const primaryName = String(primaryFile?.filename || primaryFile?.path || "")
    .split("/")
    .pop();
  const canCatalog = user?.role === "owner" || user?.role === "op";
  const canEnrichKind = work.kind === "book" || work.kind === "audiobook";
  const ribbonHoles = missingRibbonBeads(data.series_ribbon);
  const catchUpCopy = catchUpInvitation({
    seriesName: work.series_name,
    kind: work.kind,
    missingCount: ribbonHoles.length,
  });
  const catchUpHref = ribbonHoles.length
    ? findHref(
        gapFindFields({
          gap: true,
          kind: work.kind || "",
          series_name: work.series_name || "",
          missing_index: ribbonHoles[0].value,
          author: work.author || "",
        }),
      )
    : "";

  function beginFinishCeremony() {
    setFinishCeremony(true);
    setFinishWhisper("");
    setError("");
  }

  function cancelFinishCeremony() {
    if (finishSaving) return;
    setFinishCeremony(false);
    setFinishWhisper("");
  }

  async function completeFinish({ withWhisper = false, share = false } = {}) {
    if (!work?.id || finishSaving) return;
    setFinishSaving(true);
    setError("");
    try {
      const body = { finished: true, share: Boolean(share) };
      if (withWhisper && finishWhisper.trim()) {
        body.whisper = finishWhisper.trim();
        body.share = true;
      }
      const result = await api.progress(work.id, body);
      setData((prev) => {
        if (!prev) return prev;
        const next = { ...prev, progress: result.progress || prev.progress };
        if (result.whispers) next.whispers = result.whispers;
        else if (result.whisper) {
          next.whispers = [result.whisper, ...(prev.whispers || [])];
        }
        return next;
      });
      setFinishCeremony(false);
      setFinishWhisper("");
      setFinishRitual(true);
      window.setTimeout(() => setFinishRitual(false), 2200);
    } catch (err) {
      setError(humanError(err));
    } finally {
      setFinishSaving(false);
    }
  }

  function beginEdit() {
    setFixing(false);
    setMatchCandidates([]);
    setEditing(true);
    setEditDraft({
      title: work.title || "",
      author: work.author || "",
      year: work.year != null ? String(work.year) : "",
      description: work.description || "",
      genre: work.genre || "",
      series_name: work.series_name || "",
      series_index: work.series_index || "",
      kind: work.kind || "book",
      cover_url: "",
    });
    setEnrichNote("");
  }

  function patchDraft(key, value) {
    setEditDraft((prev) => ({ ...(prev || {}), [key]: value }));
  }

  async function saveEdit(event) {
    event.preventDefault();
    if (!editDraft || editSaving) return;
    setEditSaving(true);
    setEnrichNote(busyLabel("save"));
    try {
      const body = {
        title: editDraft.title,
        author: editDraft.author,
        description: editDraft.description,
        genre: editDraft.genre,
        series_name: editDraft.series_name,
        series_index: editDraft.series_index,
        kind: editDraft.kind,
      };
      const yearText = String(editDraft.year || "").trim();
      if (yearText) body.year = Number(yearText);
      else body.year = null;
      if (String(editDraft.cover_url || "").trim()) {
        body.cover_url = String(editDraft.cover_url).trim();
      }
      await api.updateWorkMetadata(work.id, body);
      const payload = await api.work(work.id);
      setData(payload);
      setEditing(false);
      setEditDraft(null);
      setEnrichNote("Catalog saved.");
    } catch (err) {
      setEnrichNote(humanError(err));
    } finally {
      setEditSaving(false);
    }
  }

  async function openFixMatch() {
    setEditing(false);
    setEditDraft(null);
    setFixing(true);
    setMatchLoading(true);
    setEnrichNote(busyLabel("match"));
    try {
      const result = await api.matchCandidates(work.id);
      setMatchCandidates(result.candidates || []);
      setEnrichNote(
        (result.candidates || []).length
          ? "Pick the correct Open Library match."
          : "No confident Open Library candidates — edit metadata by hand.",
      );
    } catch (err) {
      setEnrichNote(humanError(err));
      setMatchCandidates([]);
    } finally {
      setMatchLoading(false);
    }
  }

  async function chooseMatch(matchKey) {
    if (!matchKey || matchApplying) return;
    setMatchApplying(matchKey);
    setEnrichNote(busyLabel("match"));
    try {
      const result = await api.applyMatch(work.id, matchKey);
      const payload = await api.work(work.id);
      setData(payload);
      setFixing(false);
      setMatchCandidates([]);
      const conf =
        result.match_confidence != null ? ` · confidence ${Math.round(Number(result.match_confidence) * 100)}%` : "";
      setEnrichNote(`Applied ${result.match_key || matchKey}${conf}`);
    } catch (err) {
      setEnrichNote(humanError(err));
    } finally {
      setMatchApplying("");
    }
  }

  async function undoEnrich() {
    setEnrichNote(busyLabel("clear"));
    try {
      await api.clearEnrich(work.id);
      const payload = await api.work(work.id);
      setData(payload);
      setEnrichNote("Cleared enrich blurb.");
    } catch (err) {
      setEnrichNote(humanError(err));
    }
  }

  async function addWanted() {
    const body = availability.addBody || status.addBody;
    if (!body) return;
    setError("");
    try {
      const result = await api.addWanted(body);
      setData((prev) => (prev ? { ...prev, wanted: result.item } : prev));
    } catch (err) {
      setError(humanError(err));
    }
  }

  async function dismissWanted() {
    if (!availability.wantedId) return;
    setError("");
    try {
      const result = await api.dismissWanted(availability.wantedId);
      setData((prev) => (prev ? { ...prev, wanted: result.item } : prev));
    } catch (err) {
      setError(humanError(err));
    }
  }

  async function favorite() {
    const next = await api.favorite(work.id);
    setData({ ...data, favorite: next.favorite });
  }

  async function promote() {
    const result = await api.promote(work.id);
    if (result?.plexamp) setPlexamp(result.plexamp);
    const payload = await api.work(work.id);
    setData(payload);
  }

  async function sendWhisper(event) {
    event.preventDefault();
    setWhisperNote("");
    try {
      const result = await api.addWhisper(work.id, whisperBody);
      setData({ ...data, whispers: result.whispers || [] });
      setWhisperBody("");
    } catch (err) {
      setWhisperNote(humanError(err));
    }
  }

  return (
    <article className="work-page page-settle">
      <section className={`work-hero${data.can_download ? "" : " is-bare"}${washUrl ? " has-wash" : ""}`}>
        <div
          className={`work-hero-art${washUrl ? " has-wash" : ""}`}
          style={washStyle}
          aria-hidden="true"
          data-testid="work-hero-art"
        />
        <div className="work-hero-scrim" aria-hidden="true" />
        <div className="work-hero-inner">
          <div className="chip-row" style={{ marginBottom: 16 }}>
            {work.kind ? <span className="chip is-on">{work.kind}</span> : null}
            {work.year ? <span className="chip">{work.year}</span> : null}
            {work.author ? (
              <Link className="chip" to={browseHref({ author: work.author })} data-testid="work-author-chip">
                {work.author}
              </Link>
            ) : null}
            {work.series_name ? (
              <Link className="chip" to={browseHref({ series: work.series_name })} data-testid="work-series-chip">
                {work.series_name}
              </Link>
            ) : null}
            {work.isbn ? <span className="chip font-mono">{work.isbn}</span> : null}
            {work.review_state === "needs_review" ? <span className="chip">Needs you</span> : null}
            {work.music_state === "incoming" ? <span className="chip">Incoming</span> : null}
            {isInboundJob(work.job_status) ? <span className="chip">On the way</span> : null}
            {data.file_count > 1 ? <span className="chip">{data.file_count} files</span> : null}
            {data.favorite ? <span className="chip is-on">Favorites</span> : null}
            {work.abs_item_id ? <span className="chip">On the player</span> : null}
          </div>
          <h1>{work.title}</h1>
          <p className="work-sub">
            {[work.author, work.year, work.series_name, work.series_index].filter(Boolean).join(" · ")}
          </p>
          {work.cover_story ? (
            <p className="cover-story" data-testid="cover-story">
              {work.cover_story}
            </p>
          ) : null}
          {incompleteParts ? (
            <p className="lede" data-testid="part-set-status">
              Multipart · {partStatus}
            </p>
          ) : null}
          {mediaNote ? (
            <p className="lede work-media-note" data-testid="work-media-note">
              {mediaNote}
            </p>
          ) : null}
          <div className="cta-row compact" data-testid="work-primary" data-verb={verb || undefined}>
            {verb === "Listen" && absListenHref ? (
              <a
                className="cta compact"
                href={absListenHref}
                target="_blank"
                rel="noreferrer"
                data-testid="work-listen"
              >
                Listen
              </a>
            ) : null}
            {verb === "Listen" && !absListenHref ? (
              <button
                type="button"
                className="cta compact"
                onClick={() => openListen(bestListen?.id || "")}
                data-testid="work-listen"
              >
                Listen
              </button>
            ) : null}
            {verb === "Play" ? (
              <button type="button" className="cta compact" onClick={album.toggleAlbum} data-testid="album-play">
                {album.active ? "Stop" : "Play"}
              </button>
            ) : null}
            {verb === "Read" && canRead ? (
              <button
                type="button"
                className="cta compact"
                onClick={() => openReader(bestRead?.id || "")}
                data-testid="work-open"
              >
                Read
              </button>
            ) : null}
            {verb === "Read" && !canRead && canInlineOpen ? (
              <a
                className="cta compact"
                href={`/api/works/${work.id}/download?inline=1${fmt ? `&format=${encodeURIComponent(fmt)}` : ""}`}
                target="_blank"
                rel="noreferrer"
                data-testid="work-open"
              >
                {readLabel}
              </a>
            ) : null}
            {verb === "Download" ? (
              <a
                className="cta compact"
                href={`/api/works/${work.id}/download${fmt ? `?format=${encodeURIComponent(fmt)}` : ""}`}
                data-testid="work-download"
              >
                Download
              </a>
            ) : null}
            {verb === "Want" ? (
              <button type="button" className="cta compact" onClick={addWanted} data-testid="work-want">
                Want
              </button>
            ) : null}
            <WorkActionMenu label={work.title} testId="work-action">
              <button type="button" className="work-action-item" onClick={favorite}>
                {data.favorite ? "In Favorites" : "Favorite"}
              </button>
              {audiobookCta.show && audiobookCta.shelved ? (
                <Link className="work-action-item" to={audiobookCta.listenHref} data-testid="work-audiobook-listen">
                  {audiobookCta.secondaryLabel}
                </Link>
              ) : null}
              {audiobookCta.show && !audiobookCta.shelved ? (
                <Link className="work-action-item" to={audiobookCta.findHref} data-testid="work-find-audiobook">
                  {audiobookCta.primaryLabel}
                </Link>
              ) : null}
              {canListen && playerLink?.href ? (
                <a
                  className="work-action-item"
                  href={playerLink.href}
                  target="_blank"
                  rel="noreferrer"
                  data-testid="work-open-player"
                >
                  {playerLink.label || "Open in player"}
                </a>
              ) : null}
              {komgaLink?.href ? (
                <a
                  className="work-action-item"
                  href={komgaLink.href}
                  target="_blank"
                  rel="noreferrer"
                  data-testid="work-open-komga"
                >
                  {komgaLink.label || "Open in Komga"}
                </a>
              ) : null}
              {data.can_download ? (
                <a
                  className="work-action-item"
                  href={`/api/works/${work.id}/download${fmt ? `?format=${encodeURIComponent(fmt)}` : ""}`}
                  data-testid="work-download"
                >
                  Download
                </a>
              ) : null}
              {data.ebook_convert && work.kind === "book" ? (
                <label className="work-action-item work-action-field">
                  <span>Download format</span>
                  <select value={fmt} onChange={(e) => setFmt(e.target.value)} aria-label="Download format">
                    <option value="">Original</option>
                    {(data.formats || []).map((item) => (
                      <option key={item} value={item}>
                        {item.toUpperCase()}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              {canPromoteIncomingMusic(work, user.role) ? (
                <button type="button" className="work-action-item" onClick={promote}>
                  Promote to Plexamp
                </button>
              ) : null}
              {work.review_state === "needs_review" ? (
                <Link className="work-action-item" to={`/review?work=${encodeURIComponent(work.id)}`}>
                  Open Sorting
                </Link>
              ) : null}
              {incompleteParts ? (
                <Link
                  className="work-action-item"
                  to={findMissingHref}
                  data-testid="find-missing-parts"
                  title={partStatus || undefined}
                >
                  Find missing parts
                </Link>
              ) : null}
            </WorkActionMenu>
            {work.kind !== "music" ? (
              <button
                type="button"
                className={`cta ghost compact${finishRitual ? " finish-ritual-active" : ""}`}
                onClick={beginFinishCeremony}
                data-testid="work-finished"
                aria-expanded={finishCeremony}
                disabled={finishCeremony || finishSaving}
              >
                Finished
              </button>
            ) : null}
            {primaryName ? (
              <p className="muted font-mono" data-testid="work-file">
                {primaryName}
              </p>
            ) : null}
          </div>
          {finishCeremony ? (
            <div className="finish-ceremony" data-testid="finish-ceremony" role="region" aria-label="Finished ceremony">
              <p className="finish-ritual-note" data-testid="finish-ritual-note" role="status">
                {finishRitualCopy(hallLampPeriod())}
              </p>
              <p className="finish-whisper-invite muted">{finishWhisperInvite()}</p>
              <form
                className="finish-ceremony-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  completeFinish({ withWhisper: true, share: true });
                }}
              >
                <label className="sr-only" htmlFor="finish-whisper-body">
                  Quiet note for the house
                </label>
                <input
                  id="finish-whisper-body"
                  value={finishWhisper}
                  onChange={(e) => setFinishWhisper(e.target.value)}
                  maxLength={280}
                  placeholder="A soft word for the shelf…"
                  disabled={finishSaving}
                  data-testid="finish-whisper-input"
                />
                <div className="finish-ceremony-actions">
                  <button
                    type="submit"
                    className="cta compact"
                    disabled={finishSaving || !finishWhisper.trim()}
                    data-testid="finish-whisper-submit"
                  >
                    Whisper to the house
                  </button>
                  <button
                    type="button"
                    className="cta compact"
                    disabled={finishSaving}
                    onClick={() => completeFinish({ withWhisper: false, share: false })}
                    data-testid="finish-keep-private"
                  >
                    {FINISH_PRIVATE_LABEL}
                  </button>
                  <button
                    type="button"
                    className="cta ghost compact"
                    disabled={finishSaving}
                    onClick={() => completeFinish({ withWhisper: false, share: true })}
                    data-testid="finish-just-finished"
                  >
                    {FINISH_TELL_LABEL}
                  </button>
                  <button
                    type="button"
                    className="cta ghost compact"
                    disabled={finishSaving}
                    onClick={cancelFinishCeremony}
                  >
                    Not yet
                  </button>
                </div>
              </form>
            </div>
          ) : null}
        </div>
      </section>
      <div className="work-body">
        {Array.isArray(data.authors) && data.authors.length ? (
          <p className="muted" data-testid="work-authors">
            {data.authors
              .map((person) => person.display_name)
              .filter(Boolean)
              .join(" · ")}
          </p>
        ) : null}
        {Array.isArray(data.editions) && data.editions.length ? (
          <section aria-labelledby="work-editions-heading" data-testid="work-editions">
            <h2 id="work-editions-heading" className="kicker">
              Editions and formats
            </h2>
            <ul>
              {data.editions.map((edition) => (
                <li key={edition.id || `${edition.isbn13 || ""}-${edition.asin || ""}-${edition.format || ""}`}>
                  <span>{edition.format || edition.kind || "Edition"}</span>
                  {edition.isbn13 ? <span> ISBN {edition.isbn13}</span> : null}
                  {edition.asin ? <span> ASIN {edition.asin}</span> : null}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
        {data.files?.length ? (
          <section data-testid="work-files">
            <h2 className="kicker">{work.kind === "music" ? "Tracks" : "Files"}</h2>
            {album.nowPlayingLabel ? (
              <p className="muted album-now-playing" data-testid="now-playing">
                Playing · {album.nowPlayingLabel}
              </p>
            ) : null}
            <ul className="file-list">
              {data.files.map((file) => (
                <li
                  key={file.id}
                  className={String(album.playingId || "") === String(file.id) ? "is-playing" : undefined}
                >
                  {file.reading_room ? (
                    <button
                      type="button"
                      className="file-list-open"
                      onClick={() => openReader(file.id)}
                      data-testid="reading-room-open"
                    >
                      {file.filename}
                    </button>
                  ) : (
                    <span>{file.filename}</span>
                  )}
                  {file.reading_room ? (
                    <button
                      type="button"
                      className="chip is-on"
                      onClick={() => openReader(file.id)}
                      data-testid="reading-room-badge"
                    >
                      Reading Room
                    </button>
                  ) : null}
                  {canListen && file.on_disk !== false && isAudioFile(file) ? (
                    <button
                      type="button"
                      className="chip"
                      onClick={() => openListen(file.id)}
                      data-testid="file-listen"
                    >
                      Listen
                    </button>
                  ) : null}
                  {album.canPlayFile(file) ? (
                    <button
                      type="button"
                      className="chip"
                      onClick={() => album.toggleTrack(file.id)}
                      data-testid="track-play"
                    >
                      {String(album.playingId || "") === String(file.id) ? "Stop" : "Play"}
                    </button>
                  ) : null}
                  {data.can_download && file.on_disk !== false ? (
                    <a
                      className="chip"
                      href={workDownloadUrl(work.id, { fileId: file.id })}
                      data-testid="file-download"
                    >
                      Download
                    </a>
                  ) : null}
                  {file.on_disk === false ? <span className="chip">Missing</span> : null}
                </li>
              ))}
            </ul>
            {work.kind === "music" ? (
              <audio ref={album.audioRef} preload="none" hidden data-testid="album-audio" />
            ) : null}
          </section>
        ) : null}
        {work.description ? (
          <section className="synopsis">
            <h2>Description</h2>
            {descriptionHtml ? (
              <div
                className="synopsis-body"
                data-testid="work-description"
                dangerouslySetInnerHTML={{ __html: descriptionHtml }}
              />
            ) : (
              <p data-testid="work-description">{work.description}</p>
            )}
          </section>
        ) : null}
        <details className="advanced" data-testid="work-more">
          <summary>Series, catalog, and notes</summary>
          <div className="cta-row compact">
            <button type="button" className="cta outline compact" onClick={favorite}>
              {data.favorite ? "In Favorites" : "Favorite"}
            </button>
            {verb !== "Download" && data.can_download ? (
              <a
                className="cta outline compact"
                href={`/api/works/${work.id}/download${fmt ? `?format=${encodeURIComponent(fmt)}` : ""}`}
                data-testid="work-download"
              >
                Download
              </a>
            ) : null}
            {data.ebook_convert && work.kind === "book" ? (
              <label className="field" style={{ minWidth: "8rem" }}>
                <span className="sr-only">Download format</span>
                <select value={fmt} onChange={(e) => setFmt(e.target.value)} aria-label="Download format">
                  <option value="">Original</option>
                  {(data.formats || []).map((item) => (
                    <option key={item} value={item}>
                      {item.toUpperCase()}
                    </option>
                  ))}
                </select>
              </label>
            ) : null}
            {availability.show ? (
              <AvailabilityActions
                view={verb === "Want" ? { ...availability, canAdd: false } : availability}
                onAdd={addWanted}
                onDismiss={dismissWanted}
              />
            ) : (
              <CatalogVerb
                view={
                  verb && verb !== "Want"
                    ? { ...status, verb: "", canAdd: false }
                    : { ...status, canAdd: verb !== "Want" && status.canAdd }
                }
                onAdd={addWanted}
              />
            )}
            {canListen && playerLink?.href ? (
              <a
                className="cta outline compact"
                href={playerLink.href}
                target="_blank"
                rel="noreferrer"
                data-testid="work-open-player"
              >
                {playerLink.label || "Open in player"}
              </a>
            ) : null}
            {komgaLink?.href ? (
              <a
                className="cta outline compact"
                href={komgaLink.href}
                target="_blank"
                rel="noreferrer"
                data-testid="work-open-komga"
              >
                {komgaLink.label || "Open in Komga"}
              </a>
            ) : null}
            {canPromoteIncomingMusic(work, user.role) ? (
              <button type="button" className="cta ghost compact" onClick={promote}>
                Promote to Plexamp
              </button>
            ) : null}
            {work.review_state === "needs_review" ? (
              <Link className="cta ghost compact" to={`/review?work=${encodeURIComponent(work.id)}`}>
                Open Sorting
              </Link>
            ) : null}
            {incompleteParts ? (
              <Link
                className="cta outline compact"
                to={findMissingHref}
                data-testid="find-missing-parts"
                title={partStatus || undefined}
              >
                Find missing parts
              </Link>
            ) : null}
            <Link className="cta ghost compact" to="/">
              Back to The Hall
            </Link>
          </div>
          {finishRitual && !finishCeremony ? (
            <p className="finish-ritual-note" data-testid="finish-ritual-note" role="status">
              {finishRitualCopy(hallLampPeriod())}
            </p>
          ) : null}
          {canListen && !playerLink?.href && playerNote ? (
            <p className="muted" data-testid="work-player-note">
              {playerNote}
            </p>
          ) : null}
          {(data.series_ribbon || []).length ? (
            <section className="series-ribbon" data-testid="series-ribbon" aria-label="Series progress">
              <h2 className="kicker">Series spine</h2>
              <div className="series-ribbon-track" role="list">
                {data.series_ribbon.map((bead) => (
                  <Link
                    key={bead.value}
                    role="listitem"
                    className={`series-bead is-${bead.state}`}
                    to={
                      bead.state === "owned"
                        ? browseHref({ series: work.series_name })
                        : findHref({
                            q: `${work.series_name || ""} ${bead.value}`.trim(),
                            kind: work.kind || "",
                            series: work.series_name || "",
                            issue: bead.value,
                          })
                    }
                    title={bead.state === "owned" ? `Owned ${bead.value}` : `Find ${bead.value}`}
                    aria-label={bead.state === "owned" ? `Owned ${bead.value}` : `Find missing ${bead.value}`}
                  />
                ))}
              </div>
              {catchUpCopy ? (
                <p className="series-catch-up-invite" data-testid="series-catch-up-invite">
                  <span>{catchUpCopy}</span>
                  {catchUpHref ? (
                    <Link className="cta outline compact" to={catchUpHref}>
                      {catchUpCtaLabel(user?.role)}
                    </Link>
                  ) : null}
                </p>
              ) : null}
            </section>
          ) : null}
          {canCatalog && canEnrichKind ? (
            <section className="work-meta" data-testid="work-catalog">
              <h2 className="kicker">Catalog</h2>
              {work.series_name ? (
                <p className="muted">Series · {[work.series_name, work.series_index].filter(Boolean).join(" ")}</p>
              ) : null}
              {work.synopsis_source ? (
                <p className="muted" data-testid="work-synopsis-source">
                  Filled from {work.synopsis_source}
                  {work.genre ? ` · ${work.genre}` : ""}
                </p>
              ) : null}
              <div className="cta-row compact">
                <ThinkingButton
                  type="button"
                  className="cta outline compact"
                  busy={enriching}
                  data-testid="work-enrich"
                  onClick={async () => {
                    setEnrichNote(busyLabel("enrich"));
                    setEnriching(true);
                    try {
                      const result = await api.enrichWork(work.id);
                      const payload = await api.work(work.id);
                      setData(payload);
                      const conf =
                        result.match_confidence != null
                          ? ` · ${Math.round(Number(result.match_confidence) * 100)}%`
                          : "";
                      const key = result.match_key ? ` (${result.match_key})` : "";
                      setEnrichNote(
                        result.updated
                          ? `Filled from ${result.source || "Open Library"}${key}${conf}`
                          : result.thin
                            ? "Providers had nothing new — try Fix match, or Edit the author"
                            : "Already as complete as Hardcover and Open Library allow",
                      );
                    } catch (err) {
                      setEnrichNote(humanError(err));
                    } finally {
                      setEnriching(false);
                    }
                  }}
                >
                  Enrich
                </ThinkingButton>
                <button
                  type="button"
                  className="cta outline compact"
                  data-testid="work-edit-metadata"
                  onClick={beginEdit}
                  disabled={editing}
                >
                  Edit
                </button>
                <ThinkingButton
                  type="button"
                  className="cta outline compact"
                  data-testid="work-fix-match"
                  onClick={openFixMatch}
                  busy={matchLoading}
                >
                  Fix match
                </ThinkingButton>
                {work.description || work.synopsis_source || work.llm_blurb ? (
                  <button
                    type="button"
                    className="cta ghost compact"
                    data-testid="work-clear-enrich"
                    onClick={undoEnrich}
                  >
                    Undo enrich
                  </button>
                ) : null}
              </div>
              {editing && editDraft ? (
                <form className="catalog-edit" data-testid="work-edit-form" onSubmit={saveEdit}>
                  <label className="field">
                    <span>Title</span>
                    <input value={editDraft.title} onChange={(e) => patchDraft("title", e.target.value)} required />
                  </label>
                  <label className="field">
                    <span>Author</span>
                    <input value={editDraft.author} onChange={(e) => patchDraft("author", e.target.value)} />
                  </label>
                  <label className="field">
                    <span>Year</span>
                    <input
                      value={editDraft.year}
                      onChange={(e) => patchDraft("year", e.target.value)}
                      inputMode="numeric"
                    />
                  </label>
                  <label className="field">
                    <span>Kind</span>
                    <select value={editDraft.kind} onChange={(e) => patchDraft("kind", e.target.value)}>
                      <option value="book">book</option>
                      <option value="audiobook">audiobook</option>
                      <option value="magazine">magazine</option>
                      <option value="comic">comic</option>
                      <option value="music">music</option>
                    </select>
                  </label>
                  <label className="field">
                    <span>Genre</span>
                    <input value={editDraft.genre} onChange={(e) => patchDraft("genre", e.target.value)} />
                  </label>
                  <label className="field">
                    <span>Series</span>
                    <input value={editDraft.series_name} onChange={(e) => patchDraft("series_name", e.target.value)} />
                  </label>
                  <label className="field">
                    <span>Series index</span>
                    <input
                      value={editDraft.series_index}
                      onChange={(e) => patchDraft("series_index", e.target.value)}
                    />
                  </label>
                  <label className="field field-wide">
                    <span>Description</span>
                    <textarea
                      rows={6}
                      value={editDraft.description}
                      onChange={(e) => patchDraft("description", e.target.value)}
                    />
                  </label>
                  <label className="field field-wide">
                    <span>Cover URL</span>
                    <input
                      value={editDraft.cover_url}
                      onChange={(e) => patchDraft("cover_url", e.target.value)}
                      placeholder="Optional — downloads a new cover"
                    />
                  </label>
                  <div className="cta-row compact">
                    <button type="submit" className="cta compact" disabled={editSaving} data-testid="work-edit-save">
                      {editSaving ? busyLabel("save") : "Save"}
                    </button>
                    <button
                      type="button"
                      className="cta ghost compact"
                      onClick={() => {
                        setEditing(false);
                        setEditDraft(null);
                      }}
                    >
                      Cancel
                    </button>
                  </div>
                </form>
              ) : null}
              {fixing ? (
                <div className="match-candidates" data-testid="work-match-candidates">
                  {matchLoading ? <p className="muted">Searching Open Library…</p> : null}
                  {!matchLoading && !matchCandidates.length ? (
                    <p className="muted">No ranked candidates. Try Edit and write the blurb by hand.</p>
                  ) : null}
                  <ul className="match-candidate-list">
                    {matchCandidates.map((row) => (
                      <li key={row.match_key || `${row.title}-${row.author}`}>
                        <div>
                          <strong>{row.title}</strong>
                          <span className="muted">
                            {[row.author, row.year, row.match_key].filter(Boolean).join(" · ")}
                          </span>
                          {row.match_confidence != null ? (
                            <span className="chip">{Math.round(Number(row.match_confidence) * 100)}%</span>
                          ) : null}
                        </div>
                        <ThinkingButton
                          type="button"
                          className="cta outline compact"
                          busy={matchApplying === row.match_key}
                          disabled={Boolean(matchApplying) && matchApplying !== row.match_key}
                          data-testid="work-apply-match"
                          onClick={() => chooseMatch(row.match_key)}
                        >
                          Use this
                        </ThinkingButton>
                      </li>
                    ))}
                  </ul>
                  <button
                    type="button"
                    className="cta ghost compact"
                    onClick={() => {
                      setFixing(false);
                      setMatchCandidates([]);
                    }}
                  >
                    Close
                  </button>
                </div>
              ) : null}
              {enrichNote ? (
                <p className="muted" role="status" data-testid="work-enrich-note">
                  {enrichNote}
                </p>
              ) : null}
            </section>
          ) : work.series_name ? (
            <section className="work-meta">
              <p className="muted">Series · {[work.series_name, work.series_index].filter(Boolean).join(" ")}</p>
            </section>
          ) : null}
          <section className="family-whispers" data-testid="family-whispers">
            <h2 className="kicker">Family whispers</h2>
            <p className="muted">A short note for the household — not a social feed.</p>
            <ul className="whisper-list">
              {(data.whispers || []).map((row) => (
                <li key={row.id}>
                  <strong>{row.author_name || "Someone"}</strong>
                  <span>{row.body}</span>
                </li>
              ))}
            </ul>
            <form className="whisper-form" onSubmit={sendWhisper}>
              <label className="sr-only" htmlFor="whisper-body">
                Whisper
              </label>
              <input
                id="whisper-body"
                value={whisperBody}
                onChange={(e) => setWhisperBody(e.target.value)}
                maxLength={280}
                placeholder="Leave a quiet note…"
              />
              <button type="submit" className="cta outline compact" disabled={!whisperBody.trim()}>
                Whisper
              </button>
            </form>
            {whisperNote ? <p className="alert">{whisperNote}</p> : null}
          </section>
        </details>
      </div>
      <Rail
        title={work.author ? `More by ${work.author}` : "More on this shelf"}
        items={data.related}
        seeAllTo={work.author ? browseHref({ author: work.author }) : ""}
      />
      <WorkReaderShell rooms={rooms} data={data} />
      <WorkListenShell rooms={rooms} data={data} setData={setData} />
      {plexamp ? <PlexampToast handoff={plexamp} onClose={() => setPlexamp(null)} /> : null}
    </article>
  );
}
