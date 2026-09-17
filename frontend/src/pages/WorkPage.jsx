import { useEffect, useState } from "react";
import { Link, useOutletContext, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { browseHref } from "../browse.js";
import { coverWashStyle, coverWashUrl, isInboundJob } from "../cover.js";
import { canPromoteIncomingMusic, humanError, peekMediaNote } from "../copy.js";
import { looksLikeHtml, sanitizeDescriptionHtml } from "../description.js";
import { canOpenInlineMedia, canReadInApp } from "../reader.js";
import Rail from "../components/Rail.jsx";
import Reader from "../components/Reader.jsx";

export default function WorkPage() {
  const { id } = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user } = useOutletContext();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [fmt, setFmt] = useState("");
  const [enriching, setEnriching] = useState(false);
  const [enrichNote, setEnrichNote] = useState("");
  const [reading, setReading] = useState(false);

  useEffect(() => {
    api
      .work(id)
      .then((payload) => {
        setData(payload);
        if (payload?.work?.id) {
          api.progress(payload.work.id).catch(() => {});
        }
      })
      .catch((err) => setError(humanError(err)));
  }, [id]);

  useEffect(() => {
    if (!data) return;
    const readable = Boolean(data.can_read) && canReadInApp(data.work, data.files);
    if (searchParams.get("read") === "1" && readable) setReading(true);
  }, [searchParams, data]);

  function closeReader() {
    setReading(false);
    if (searchParams.get("read")) {
      const next = new URLSearchParams(searchParams);
      next.delete("read");
      setSearchParams(next, { replace: true });
    }
  }

  if (error) {
    return (
      <div className="admin-room">
        <p className="alert">{error}</p>
      </div>
    );
  }
  if (!data) return <p className="lede" style={{ padding: "var(--space-8) var(--gutter)" }}>Opening the volume…</p>;

  const work = data.work;
  const canRead = Boolean(data.can_read) && canReadInApp(work, data.files);
  const canInlineOpen = canOpenInlineMedia(work, Boolean(data.can_download), canRead);
  const mediaNote = peekMediaNote(work, { canDownload: Boolean(data.can_download), ready: true });
  const descriptionHtml = looksLikeHtml(work.description) ? sanitizeDescriptionHtml(work.description) : "";
  const washUrl = coverWashUrl(work);
  const washStyle = coverWashStyle(work);

  async function favorite() {
    const next = await api.favorite(work.id);
    setData({ ...data, favorite: next.favorite });
  }

  async function promote() {
    await api.promote(work.id);
    const payload = await api.work(work.id);
    setData(payload);
  }

  return (
    <article>
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
          {mediaNote ? (
            <p className="lede work-media-note" data-testid="work-media-note">
              {mediaNote}
            </p>
          ) : null}
          <div className="cta-row compact">
            <button type="button" className="cta outline compact" onClick={favorite}>
              {data.favorite ? "In Favorites" : "Favorite"}
            </button>
            {canRead ? (
              <button type="button" className="cta compact" onClick={() => setReading(true)} data-testid="work-open">
                Open
              </button>
            ) : canInlineOpen ? (
              <a
                className="cta compact"
                href={`/api/works/${work.id}/download?inline=1${fmt ? `&format=${encodeURIComponent(fmt)}` : ""}`}
                target="_blank"
                rel="noreferrer"
                data-testid="work-open"
              >
                Open
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
              <button type="button" className="cta ghost compact" onClick={() => api.progress(work.id, { finished: true })}>
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
            <Link className="cta ghost compact" to="/">
              Back to The Hall
            </Link>
          </div>
        </div>
      </section>
      <div className="work-body">
        {user?.role === "owner" && (work.kind === "book" || work.kind === "audiobook") ? (
          <section className="work-meta">
            <h2 className="kicker">Catalog</h2>
            {work.series_name ? (
              <p className="muted">
                Series · {[work.series_name, work.series_index].filter(Boolean).join(" ")}
              </p>
            ) : null}
            <div className="cta-row compact">
              <button
                type="button"
                className="cta outline compact"
                disabled={enriching}
                onClick={async () => {
                  setEnrichNote("");
                  setEnriching(true);
                  try {
                    const result = await api.enrichWork(work.id);
                    const payload = await api.work(work.id);
                    setData(payload);
                    setEnrichNote(
                      result.updated
                        ? `Filled from ${result.source || "Open Library"}`
                        : "Already as complete as Hardcover and Open Library allow",
                    );
                  } catch (err) {
                    setEnrichNote(humanError(err));
                  } finally {
                    setEnriching(false);
                  }
                }}
              >
                {enriching ? "Enriching…" : "Enrich"}
              </button>
            </div>
            {enrichNote ? <p className="muted">{enrichNote}</p> : null}
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
        {data.files?.length ? (
          <section>
            <h2 className="kicker">Files</h2>
            <ul className="file-list">
              {data.files.map((file) => (
                <li key={file.id}>
                  <span>{file.filename}</span>
                  {file.reading_room ? (
                    <span className="chip is-on" data-testid="reading-room-badge">
                      Reading Room
                    </span>
                  ) : null}
                  {file.on_disk === false ? <span className="chip">Missing</span> : null}
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </div>
      <Rail
        title={work.author ? `More by ${work.author}` : "More on this shelf"}
        items={data.related}
        seeAllTo={work.author ? browseHref({ author: work.author }) : ""}
      />
      {reading && canRead ? (
        <Reader work={work} files={data.files} progress={data.progress} onClose={closeReader} />
      ) : null}
    </article>
  );
}
