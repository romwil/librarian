import { useEffect, useState } from "react";
import { Link, useOutletContext, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { busyLabel } from "../actionBusy.js";
import { browseHref } from "../browse.js";
import { coverWashStyle, coverWashUrl, isInboundJob } from "../cover.js";
import { canPromoteIncomingMusic, humanError, peekMediaNote } from "../copy.js";
import { looksLikeHtml, sanitizeDescriptionHtml } from "../description.js";
import { findHref } from "../find.js";
import { companionAudiobookView } from "../audiobookCompanion.js";
import { isIncompleteOwnedPartSet, ownedPartSetStatusLine, partSetFindFields } from "../findParts.js";
import { useAlbumPlayer } from "../hooks/useAlbumPlayer.js";
import { finishRitualCopy } from "../lib/lampRituals.js";
import { canListenInApp, isAudioFile } from "../listen.js";
import { canOpenInlineMedia, canReadInApp, readerCtaLabel, workDownloadUrl } from "../reader.js";
import Rail from "../components/Rail.jsx";
import Reader from "../components/Reader.jsx";
import AudiobookPlayer from "../components/AudiobookPlayer.jsx";
import PlexampToast from "../components/PlexampToast.jsx";
import WarmLoad from "../components/WarmLoad.jsx";

export default function WorkPage() {
  const { id } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
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
  const [reading, setReading] = useState(false);
  const [readingFileId, setReadingFileId] = useState("");
  const [listening, setListening] = useState(false);
  const [listeningFileId, setListeningFileId] = useState("");
  const [whisperBody, setWhisperBody] = useState("");
  const [whisperNote, setWhisperNote] = useState("");
  const [plexamp, setPlexamp] = useState(null);
  const [finishRitual, setFinishRitual] = useState(false);
  const album = useAlbumPlayer({
    workId: id,
    files: data?.files || [],
    enabled: Boolean(data?.can_download && data?.work?.kind === "music"),
  });

  useEffect(() => {
    api
      .work(id)
      .then((payload) => {
        setData(payload);
        // Books/comics leave a Continue bookmark on open; audiobooks only on real Listen progress.
        if (payload?.work?.id && payload.work.kind !== "audiobook") {
          api.progress(payload.work.id).catch(() => {});
        }
      })
      .catch((err) => setError(humanError(err)));
  }, [id]);

  useEffect(() => {
    if (!data) return;
    const readable = Boolean(data.can_read) && canReadInApp(data.work, data.files);
    const listenable =
      Boolean(data.listen?.can_listen) && canListenInApp(data.work, data.files, Boolean(data.can_download));
    if (searchParams.get("listen") === "1" && listenable) {
      setListeningFileId(searchParams.get("file") || "");
      setListening(true);
      return;
    }
    if (searchParams.get("read") === "1" && readable) {
      setReadingFileId(searchParams.get("file") || "");
      setReading(true);
    }
  }, [searchParams, data]);

  function openReader(fileId = "") {
    const wanted = String(fileId || "").trim();
    setReadingFileId(wanted);
    setReading(true);
    // Shareable deep link — same `?read=1&file=` contract as WorkPeek (`workReaderPath`).
    const next = new URLSearchParams(searchParams);
    next.delete("listen");
    next.set("read", "1");
    if (wanted) next.set("file", wanted);
    else next.delete("file");
    setSearchParams(next, { replace: true });
  }

  function closeReader() {
    setReading(false);
    setReadingFileId("");
    if (searchParams.get("read") || searchParams.get("file")) {
      const next = new URLSearchParams(searchParams);
      next.delete("read");
      next.delete("file");
      setSearchParams(next, { replace: true });
    }
  }

  async function openListen(fileId = "") {
    const wanted = String(fileId || "").trim();
    setListeningFileId(wanted);
    // Refresh per-user progress so resume is not stale after a prior Listen session.
    try {
      const fresh = await api.work(id);
      setData(fresh);
    } catch {
      /* keep existing payload */
    }
    setListening(true);
    const next = new URLSearchParams(searchParams);
    next.delete("read");
    next.set("listen", "1");
    if (wanted) next.set("file", wanted);
    else next.delete("file");
    setSearchParams(next, { replace: true });
  }

  function closeListen() {
    setListening(false);
    setListeningFileId("");
    if (searchParams.get("listen") || searchParams.get("file")) {
      const next = new URLSearchParams(searchParams);
      next.delete("listen");
      next.delete("file");
      setSearchParams(next, { replace: true });
    }
    api.work(id).then(setData).catch(() => {});
  }

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
  const canRead = Boolean(data.can_read) && canReadInApp(work, data.files);
  const canListen =
    Boolean(data.listen?.can_listen) && canListenInApp(work, data.files, Boolean(data.can_download));
  const listenResume = Boolean(String(data.progress?.position || "").trim()) || Number(data.progress?.fraction) > 0;
  const canInlineOpen = canOpenInlineMedia(work, Boolean(data.can_download), canRead);
  const playerLink = data.listen?.player || null;
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
  const readLabel = readerCtaLabel(work) || "Read";
  const canCatalog = user?.role === "owner" || user?.role === "op";
  const canEnrichKind = work.kind === "book" || work.kind === "audiobook";

  async function markFinished() {
    try {
      await api.progress(work.id, { finished: true });
      setFinishRitual(true);
      window.setTimeout(() => setFinishRitual(false), 1800);
    } catch (err) {
      setError(humanError(err));
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
            {work.review_state === "needs_review" ? <span className="chip">Review</span> : null}
            {work.music_state === "incoming" ? <span className="chip">Incoming</span> : null}
            {isInboundJob(work.job_status) ? <span className="chip">On the way</span> : null}
            {data.file_count > 1 ? <span className="chip">{data.file_count} files</span> : null}
            {data.favorite ? <span className="chip is-on">Favorites</span> : null}
            {work.abs_item_id ? <span className="chip">On the player</span> : null}
          </div>
          <h1>{work.title}</h1>
          <p className="work-sub">{[work.author, work.year, work.series_name, work.series_index].filter(Boolean).join(" · ")}</p>
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
          <div className="cta-row compact">
            <button type="button" className="cta outline compact" onClick={favorite}>
              {data.favorite ? "In Favorites" : "Favorite"}
            </button>
            {canListen ? (
              <button type="button" className="cta compact" onClick={() => openListen()} data-testid="work-listen">
                {listenResume ? "Continue listening" : "Listen"}
              </button>
            ) : album.enabled ? (
              <button
                type="button"
                className="cta compact"
                onClick={album.toggleAlbum}
                data-testid="album-play"
              >
                {album.active ? "Stop" : "Play"}
              </button>
            ) : canRead ? (
              <button type="button" className="cta compact" onClick={() => openReader()} data-testid="work-open">
                {readLabel}
              </button>
            ) : canInlineOpen ? (
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
            {audiobookCta.show && audiobookCta.shelved ? (
              <Link
                className="cta outline compact"
                to={audiobookCta.listenHref}
                data-testid="work-audiobook-listen"
              >
                {audiobookCta.secondaryLabel}
              </Link>
            ) : null}
            {audiobookCta.show && !audiobookCta.shelved ? (
              <Link className="cta outline compact" to={audiobookCta.findHref} data-testid="work-find-audiobook">
                {audiobookCta.primaryLabel}
              </Link>
            ) : null}
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
            {data.can_download ? (
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
            {work.kind !== "music" ? (
              <button
                type="button"
                className={`cta ghost compact${finishRitual ? " finish-ritual-active" : ""}`}
                onClick={markFinished}
                data-testid="work-finished"
              >
                Finished
              </button>
            ) : null}
            {canPromoteIncomingMusic(work, user.role) ? (
              <button type="button" className="cta ghost compact" onClick={promote}>
                Promote to Plexamp
              </button>
            ) : null}
            {work.review_state === "needs_review" ? (
              <Link className="cta ghost compact" to={`/review?work=${encodeURIComponent(work.id)}`}>
                Open Review
              </Link>
            ) : null}
            {incompleteParts ? (
              <Link
                className="cta compact"
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
          {finishRitual ? (
            <p className="finish-ritual-note" data-testid="finish-ritual-note" role="status">
              {finishRitualCopy()}
            </p>
          ) : null}
          {canListen && !playerLink?.href && playerNote ? (
            <p className="muted" data-testid="work-player-note">
              {playerNote}
            </p>
          ) : null}
        </div>
      </section>
      <div className="work-body">
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
          </section>
        ) : null}
        {canCatalog && canEnrichKind ? (
          <section className="work-meta" data-testid="work-catalog">
            <h2 className="kicker">Catalog</h2>
            {work.series_name ? (
              <p className="muted">
                Series · {[work.series_name, work.series_index].filter(Boolean).join(" ")}
              </p>
            ) : null}
            {work.synopsis_source ? (
              <p className="muted" data-testid="work-synopsis-source">
                Filled from {work.synopsis_source}
                {work.genre ? ` · ${work.genre}` : ""}
              </p>
            ) : null}
            <div className="cta-row compact">
              <button
                type="button"
                className="cta outline compact"
                disabled={enriching}
                aria-busy={enriching || undefined}
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
                        : "Already as complete as Hardcover and Open Library allow",
                    );
                  } catch (err) {
                    setEnrichNote(humanError(err));
                  } finally {
                    setEnriching(false);
                  }
                }}
              >
                {enriching ? busyLabel("enrich") : "Enrich"}
              </button>
              <button
                type="button"
                className="cta outline compact"
                data-testid="work-edit-metadata"
                onClick={beginEdit}
                disabled={editing}
              >
                Edit
              </button>
              <button
                type="button"
                className="cta outline compact"
                data-testid="work-fix-match"
                onClick={openFixMatch}
                disabled={matchLoading}
              >
                {matchLoading ? busyLabel("match") : "Fix match"}
              </button>
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
                      <button
                        type="button"
                        className="cta outline compact"
                        disabled={Boolean(matchApplying)}
                        data-testid="work-apply-match"
                        onClick={() => chooseMatch(row.match_key)}
                      >
                        {matchApplying === row.match_key ? busyLabel("match") : "Use this"}
                      </button>
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
            <p className="muted">
              Series · {[work.series_name, work.series_index].filter(Boolean).join(" ")}
            </p>
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
        {data.files?.length ? (
          <section>
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
      </div>
      <Rail
        title={work.author ? `More by ${work.author}` : "More on this shelf"}
        items={data.related}
        seeAllTo={work.author ? browseHref({ author: work.author }) : ""}
      />
      {reading && canRead ? (
        <Reader
          work={work}
          files={data.files}
          fileId={readingFileId}
          progress={data.progress}
          onClose={closeReader}
        />
      ) : null}
      {listening && canListen ? (
        <AudiobookPlayer
          work={work}
          files={data.files}
          fileId={listeningFileId}
          progress={data.progress}
          player={playerLink}
          playerNote={playerNote}
          onClose={closeListen}
          onProgress={(row) => setData((prev) => (prev ? { ...prev, progress: row } : prev))}
        />
      ) : null}
      {plexamp ? <PlexampToast handoff={plexamp} onClose={() => setPlexamp(null)} /> : null}
    </article>
  );
}
