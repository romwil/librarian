import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { humanError } from "../copy.js";
import {
  bestsellersHref,
  nytHitFindHref,
  nytHitHref,
  requestBodyFromHit,
} from "../find.js";
import { useWorkPeek } from "./WorkPeekProvider.jsx";

function bookKey(book = {}) {
  return `${book.title || ""}|${book.author || ""}|${book.isbn || ""}|${book.rank || ""}`;
}

export default function BestsellersPanel({ list = "hardcover-fiction", date = "current", embedded = false }) {
  const navigate = useNavigate();
  const peek = useWorkPeek();
  const [names, setNames] = useState([]);
  const [payload, setPayload] = useState(null);
  const [phase, setPhase] = useState("loading");
  const [error, setError] = useState("");
  const [listSlug, setListSlug] = useState(list || "hardcover-fiction");
  const [listDate, setListDate] = useState(date || "current");
  const [selected, setSelected] = useState(() => new Set());
  const [chasePhase, setChasePhase] = useState("idle");
  const [chaseByKey, setChaseByKey] = useState({});
  const [requestJobs, setRequestJobs] = useState({});
  const [requestError, setRequestError] = useState("");

  useEffect(() => {
    setListSlug(list || "hardcover-fiction");
    setListDate(date || "current");
  }, [list, date]);

  useEffect(() => {
    let alive = true;
    api
      .listPresets()
      .then((data) => {
        if (!alive) return;
        setNames(data.presets || []);
      })
      .catch(() => {
        if (!alive) return;
        setNames([]);
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    let alive = true;
    setPhase("loading");
    setError("");
    setSelected(new Set());
    setChaseByKey({});
    setChasePhase("idle");
    setRequestJobs({});
    api
      .llmList({ preset: listSlug, date: listDate })
      .then((data) => {
        if (!alive) return;
        setPayload(data);
        const missingKeys = (data.missing || []).map(bookKey);
        setSelected(new Set(missingKeys));
        setPhase("done");
      })
      .catch((err) => {
        if (!alive) return;
        setPayload(null);
        setError(humanError(err));
        setPhase("error");
      });
    return () => {
      alive = false;
    };
  }, [listSlug, listDate]);

  function selectList(next) {
    const slug = String(next || "").trim() || "hardcover-fiction";
    setListSlug(slug);
    navigate(bestsellersHref({ list: slug, date: listDate }), { replace: true });
  }

  function onDateChange(event) {
    const raw = String(event.target.value || "").trim();
    const next = raw || "current";
    setListDate(next);
    navigate(bestsellersHref({ list: listSlug, date: next }), { replace: true });
  }

  function toggleSelected(key) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key);
      else next.add(key);
      return next;
    });
  }

  const books = payload?.books || [];
  const missing = useMemo(() => books.filter((book) => !book.shelved?.id), [books]);
  const missingSelected = useMemo(
    () => missing.filter((book) => selected.has(bookKey(book))),
    [missing, selected],
  );
  const emptyCopy =
    payload?.empty_copy ||
    (phase === "done" && !books.length ? "No titles on this list yet." : "");
  const canRequest = Boolean(payload?.can_request);
  const chasedCount = Object.keys(chaseByKey).length;

  async function chaseMissing() {
    if (!missingSelected.length) return;
    setChasePhase("searching");
    setRequestError("");
    try {
      const data = await api.llmListChase(
        missingSelected.map((book) => ({
          title: book.title,
          author: book.author,
          isbn: book.isbn || "",
        })),
      );
      const byTitleAuthor = {};
      for (const row of data.results || []) {
        byTitleAuthor[`${String(row.title || "").toLowerCase()}|${String(row.author || "").toLowerCase()}`] =
          row;
      }
      const mapped = {};
      for (const book of missingSelected) {
        const hit =
          byTitleAuthor[`${String(book.title || "").toLowerCase()}|${String(book.author || "").toLowerCase()}`];
        if (hit) mapped[bookKey(book)] = hit;
      }
      setChaseByKey(mapped);
      setChasePhase("done");
    } catch (err) {
      setChasePhase("error");
      setRequestError(humanError(err));
    }
  }

  async function requestHit(hit, sought, jobKey) {
    if (!hit?.guid || !canRequest) return;
    setRequestError("");
    try {
      const data = await api.requestItem(requestBodyFromHit(hit, sought));
      setRequestJobs((prev) => ({ ...prev, [jobKey]: data.job?.status || "asked" }));
    } catch (err) {
      setRequestError(humanError(err));
    }
  }

  return (
    <section className={`bestsellers-panel${embedded ? " is-embedded" : ""}`} data-testid="bestsellers-panel">
      <header className="bestsellers-head">
        <div>
          <p className="kicker">Bestsellers · curated lists</p>
          <h2>{payload?.display_name || "Bestsellers"}</h2>
          <p className="lede">
            BYO LLM names the list · shelves first · Find book and audiobook for misses · Confirm before SAB.
            {payload?.published_date ? ` · Published ${payload.published_date}` : ""}
          </p>
        </div>
        <label className="field bestsellers-date">
          <span className="kicker">Closest to date</span>
          <input
            type="date"
            value={listDate === "current" ? "" : listDate}
            onChange={onDateChange}
            aria-label="Bestseller list date"
            data-testid="bestsellers-date"
          />
          <button
            type="button"
            className="cta ghost compact"
            onClick={() => {
              setListDate("current");
              navigate(bestsellersHref({ list: listSlug, date: "current" }), { replace: true });
            }}
            data-testid="bestsellers-current"
          >
            Most recent
          </button>
        </label>
      </header>
      {names.length ? (
        <div className="search-hero chip-row" data-testid="bestsellers-cats">
          {names.map((row) => (
            <button
              key={row.list_name_encoded || row.id}
              type="button"
              className={`chip${listSlug === (row.list_name_encoded || row.id) ? " is-on" : ""}`}
              aria-pressed={listSlug === (row.list_name_encoded || row.id)}
              onClick={() => selectList(row.list_name_encoded || row.id)}
            >
              {row.display_name || row.list_name_encoded}
            </button>
          ))}
        </div>
      ) : null}
      {error ? (
        <p className="alert" role="status">
          {error}
        </p>
      ) : null}
      {requestError ? (
        <p className="alert" role="status">
          {requestError}
        </p>
      ) : null}
      {phase === "loading" ? <p className="lede">Turning the list pages…</p> : null}
      {emptyCopy && phase !== "loading" ? (
        <p className="lede" data-testid="bestsellers-empty">
          {emptyCopy}
        </p>
      ) : null}
      {missing.length && phase === "done" ? (
        <div className="bestsellers-batch cta-row" data-testid="bestsellers-batch">
          <button
            type="button"
            className="cta compact"
            disabled={!missingSelected.length || chasePhase === "searching"}
            onClick={chaseMissing}
            data-testid="bestsellers-request-missing"
          >
            {chasePhase === "searching"
              ? "Looking beyond the shelves…"
              : `Request missing (${missingSelected.length})`}
          </button>
          <p className="muted">
            Finds ebook and audiobook hits for the selected gaps. Nothing queues until you Confirm each Request.
          </p>
        </div>
      ) : null}
      {chasePhase === "done" && chasedCount ? (
        <p className="lede" data-testid="bestsellers-chase-ready">
          Hits ready below — Request the book, and the audiobook when one is listed.
        </p>
      ) : null}
      {books.length ? (
        <ol className="bestsellers-list" data-testid="bestsellers-list">
          {books.map((book) => {
            const key = bookKey(book);
            const href = nytHitHref(book);
            const findHrefValue = nytHitFindHref(book);
            const shelved = Boolean(book.shelved?.id);
            const audioShelved = Boolean(book.shelved_audiobook?.id);
            const chase = chaseByKey[key];
            const bookJob = requestJobs[`${key}:book`];
            const audioJob = requestJobs[`${key}:audiobook`];
            return (
              <li key={key} className="bestsellers-row">
                <span className="bestsellers-rank" aria-hidden="true">
                  {!shelved ? (
                    <input
                      type="checkbox"
                      checked={selected.has(key)}
                      onChange={() => toggleSelected(key)}
                      aria-label={`Select ${book.title}`}
                      data-testid="bestsellers-select"
                    />
                  ) : (
                    book.rank || "·"
                  )}
                </span>
                <div className="bestsellers-cover" aria-hidden="true">
                  {book.cover ? <img src={book.cover} alt="" /> : <span className="bestsellers-cover-blank" />}
                </div>
                <div className="bestsellers-copy">
                  <Link
                    to={href}
                    className="bestsellers-title"
                    onClick={(event) => {
                      if (shelved && peek?.openWork && !event.metaKey && !event.ctrlKey) {
                        event.preventDefault();
                        peek.openWork(book.shelved, { triggerEl: event.currentTarget });
                      }
                    }}
                  >
                    {book.title}
                  </Link>
                  <p className="muted">{[book.author, book.publisher].filter(Boolean).join(" · ")}</p>
                  <div className="cta-row compact">
                    {shelved ? (
                      <Link className="cta compact" to={href} data-testid="bestsellers-shelved">
                        On the shelves
                      </Link>
                    ) : (
                      <>
                        <Link className="cta compact" to={href} data-testid="bestsellers-search">
                          Search shelves
                        </Link>
                        <Link className="cta outline compact" to={findHrefValue} data-testid="bestsellers-find">
                          Find beyond
                        </Link>
                      </>
                    )}
                    {audioShelved ? (
                      <Link
                        className="cta outline compact"
                        to={`/works/${encodeURIComponent(book.shelved_audiobook.id)}`}
                        data-testid="bestsellers-audio-shelved"
                      >
                        Audiobook on the shelves
                      </Link>
                    ) : null}
                  </div>
                  {chase ? (
                    <div className="bestsellers-chase cta-row compact" data-testid="bestsellers-chase">
                      {chase.book_hit?.guid ? (
                        <button
                          type="button"
                          className="cta compact"
                          disabled={Boolean(bookJob) || !canRequest}
                          onClick={() =>
                            requestHit(chase.book_hit, chase.sought?.book || { kind: "book", ...book }, `${key}:book`)
                          }
                          data-testid="bestsellers-request-book"
                        >
                          {bookJob ? (bookJob === "asked" ? "Asked" : "Queued") : "Request book"}
                        </button>
                      ) : (
                        <span className="muted">No ebook hit yet</span>
                      )}
                      {chase.audiobook_hit?.guid ? (
                        <button
                          type="button"
                          className="cta outline compact"
                          disabled={Boolean(audioJob) || !canRequest}
                          onClick={() =>
                            requestHit(
                              chase.audiobook_hit,
                              chase.sought?.audiobook || { kind: "audiobook", ...book },
                              `${key}:audiobook`,
                            )
                          }
                          data-testid="bestsellers-request-audiobook"
                        >
                          {audioJob
                            ? audioJob === "asked"
                              ? "Asked"
                              : "Queued"
                            : "Audiobook available to request"}
                        </button>
                      ) : chase.audiobook_available === false ? (
                        <span className="muted">No audiobook hit</span>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ol>
      ) : null}
    </section>
  );
}
