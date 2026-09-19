import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import {
  chaseCandidateRows,
  chaseConversationLines,
  chaseResultRows,
  chaseStepLines,
  chaseTraceSummary,
} from "../chaseTrace.js";
import { humanError } from "../copy.js";
import { jobChipTone, jobHouseholdLabel, listRowCoverUrl } from "../cover.js";
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

function StatusChip({ status, lane = "" }) {
  const label = jobHouseholdLabel(status);
  if (!label) return null;
  const tone = jobChipTone(status);
  const text = lane ? `${lane} · ${label}` : label;
  return (
    <span className={`live-chip bestsellers-status${tone ? ` ${tone}` : ""}`} data-testid="bestsellers-job-status">
      {text}
    </span>
  );
}

function ListCover({ book, chase }) {
  const src = listRowCoverUrl(book, chase);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setFailed(false);
  }, [src]);
  const show = Boolean(src) && !failed;
  return (
    <div className="bestsellers-cover" aria-hidden="true">
      {show ? (
        <img
          src={src}
          alt=""
          loading="lazy"
          onError={() => setFailed(true)}
          onLoad={(event) => {
            // Open Library serves a 1×1 placeholder when no cover exists.
            if (event.currentTarget.naturalWidth < 3) setFailed(true);
          }}
        />
      ) : (
        <span className="bestsellers-cover-blank" />
      )}
    </div>
  );
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
  const [batchNote, setBatchNote] = useState("");

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
    setBatchNote("");
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
  const rawEmpty =
    payload?.empty_copy ||
    (phase === "done" && !books.length ? "No titles on this list yet." : "");
  const emptyCopy = rawEmpty ? humanError(rawEmpty) : "";
  const canRequest = Boolean(payload?.can_request);
  const chasedCount = Object.keys(chaseByKey).length;
  const batchBusy = chasePhase === "searching" || chasePhase === "requesting";
  const requestedCount = Object.keys(requestJobs).length;

  async function requestHit(hit, sought, jobKey, chaseRow = null) {
    if (!hit?.guid || !canRequest) return null;
    const lane = String(jobKey).endsWith(":audiobook") ? "audiobook" : "book";
    const candidates =
      hit.candidates ||
      chaseRow?.[`${lane}_candidates`] ||
      chaseRow?.trace?.[lane]?.candidates ||
      [];
    const data = await api.requestItem(
      requestBodyFromHit(hit, sought, {
        candidates,
        rank_method: hit.rank_method || chaseRow?.trace?.[lane]?.rank_method || "",
        rank_reason: hit.rank_reason || chaseRow?.trace?.[lane]?.rank_reason || "",
      }),
    );
    const status = data.job?.status || "asked";
    setRequestJobs((prev) => ({ ...prev, [jobKey]: status }));
    return status;
  }

  async function requestMissing() {
    if (!missingSelected.length || batchBusy) return;
    setChasePhase("searching");
    setBatchNote("Searching…");
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

      const pending = [];
      for (const book of missingSelected) {
        const key = bookKey(book);
        const chase = mapped[key];
        if (!chase) continue;
        if (chase.book_hit?.guid) {
          pending.push({
            hit: chase.book_hit,
            sought: chase.sought?.book || { kind: "book", title: book.title, author: book.author, isbn: book.isbn },
            jobKey: `${key}:book`,
            chase,
          });
        }
        if (chase.audiobook_hit?.guid) {
          pending.push({
            hit: chase.audiobook_hit,
            sought:
              chase.sought?.audiobook || {
                kind: "audiobook",
                title: book.title,
                author: book.author,
                isbn: book.isbn,
              },
            jobKey: `${key}:audiobook`,
            chase,
          });
        }
      }

      const toRequest = pending.filter((row) => !requestJobs[row.jobKey]);
      if (!toRequest.length) {
        setChasePhase("done");
        setBatchNote(
          Object.keys(mapped).length
            ? "Find finished — no new hits with a guid to request."
            : "Find finished — nothing beyond the shelves yet.",
        );
        return;
      }
      if (!canRequest) {
        setChasePhase("done");
        setBatchNote("Hits ready below — you cannot request from this account.");
        return;
      }

      setChasePhase("requesting");
      let filed = 0;
      for (let index = 0; index < toRequest.length; index += 1) {
        const row = toRequest[index];
        setBatchNote(`Requesting ${index + 1}/${toRequest.length}…`);
        try {
          await requestHit(row.hit, row.sought, row.jobKey, row.chase);
          filed += 1;
        } catch (err) {
          setRequestError(humanError(err));
        }
      }
      setChasePhase("done");
      setBatchNote(
        filed
          ? `Requested ${filed} of ${toRequest.length} — status on each row.`
          : "Find finished — requests did not go through.",
      );
    } catch (err) {
      setChasePhase("error");
      setBatchNote("");
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
            BYO LLM names the list · shelves first · Request missing Finds and requests book and audiobook hits.
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
        <div className="bestsellers-batch" data-testid="bestsellers-batch">
          <button
            type="button"
            className="cta compact"
            disabled={!missingSelected.length || batchBusy}
            aria-busy={batchBusy || undefined}
            onClick={requestMissing}
            data-testid="bestsellers-request-missing"
          >
            {chasePhase === "searching"
              ? "Searching…"
              : chasePhase === "requesting"
                ? batchNote || "Requesting…"
                : `Request missing (${missingSelected.length})`}
          </button>
          <p className="muted">
            Finds ebook and audiobook hits for the selected gaps, then requests each hit found (owners/ops queue SAB;
            readers file Asked slips).
          </p>
          {batchNote ? (
            <p className="lede" role="status" data-testid="bestsellers-batch-note">
              {batchNote}
            </p>
          ) : null}
        </div>
      ) : null}
      {chasePhase === "done" && chasedCount && !batchNote ? (
        <p className="lede" data-testid="bestsellers-chase-ready">
          {requestedCount
            ? "Requested what Find found — status on each row."
            : "Hits ready below — Request the book, and the audiobook when one is listed."}
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
              <li key={key} className={`bestsellers-row${shelved ? " is-shelved" : ""}`}>
                <div className="bestsellers-rank-col">
                  {!shelved ? (
                    <input
                      type="checkbox"
                      className="bestsellers-select"
                      checked={selected.has(key)}
                      onChange={() => toggleSelected(key)}
                      disabled={batchBusy}
                      aria-label={`Select ${book.title}`}
                      data-testid="bestsellers-select"
                    />
                  ) : (
                    <span className="bestsellers-select-spacer" aria-hidden="true" />
                  )}
                  <span className="bestsellers-rank" aria-hidden="true">
                    {book.rank || "·"}
                  </span>
                </div>
                <ListCover book={book} chase={chase} />
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
                  <p className="muted bestsellers-byline">
                    {[book.author, book.publisher].filter(Boolean).join(" · ")}
                  </p>
                  <div className="bestsellers-actions">
                    {shelved ? (
                      <Link className="bestsellers-link is-solid" to={href} data-testid="bestsellers-shelved">
                        On the shelves
                      </Link>
                    ) : (
                      <>
                        <Link className="bestsellers-link" to={href} data-testid="bestsellers-search">
                          Search shelves
                        </Link>
                        <Link className="bestsellers-link" to={findHrefValue} data-testid="bestsellers-find">
                          Find beyond
                        </Link>
                      </>
                    )}
                    {audioShelved ? (
                      <Link
                        className="bestsellers-link"
                        to={`/works/${encodeURIComponent(book.shelved_audiobook.id)}`}
                        data-testid="bestsellers-audio-shelved"
                      >
                        Audiobook on the shelves
                      </Link>
                    ) : null}
                  </div>
                  {chase ? (
                    <div className="bestsellers-chase" data-testid="bestsellers-chase">
                      {chase.book_hit?.guid ? (
                        bookJob ? (
                          <StatusChip status={bookJob} lane="Book" />
                        ) : (
                          <button
                            type="button"
                            className="cta compact"
                            disabled={!canRequest || batchBusy}
                            onClick={() => {
                              setRequestError("");
                              requestHit(
                                chase.book_hit,
                                chase.sought?.book || {
                                  kind: "book",
                                  title: book.title,
                                  author: book.author,
                                  isbn: book.isbn,
                                },
                                `${key}:book`,
                                chase,
                              ).catch((err) => setRequestError(humanError(err)));
                            }}
                            data-testid="bestsellers-request-book"
                          >
                            Request book
                          </button>
                        )
                      ) : (
                        <span className="muted">
                          {chase.book_error ? `Ebook: ${chase.book_error}` : "No ebook hit yet"}
                        </span>
                      )}
                      {chase.audiobook_hit?.guid ? (
                        audioJob ? (
                          <StatusChip status={audioJob} lane="Audiobook" />
                        ) : (
                          <button
                            type="button"
                            className="cta outline compact"
                            disabled={!canRequest || batchBusy}
                            onClick={() => {
                              setRequestError("");
                              requestHit(
                                chase.audiobook_hit,
                                chase.sought?.audiobook || {
                                  kind: "audiobook",
                                  title: book.title,
                                  author: book.author,
                                  isbn: book.isbn,
                                },
                                `${key}:audiobook`,
                                chase,
                              ).catch((err) => setRequestError(humanError(err)));
                            }}
                            data-testid="bestsellers-request-audiobook"
                          >
                            Request audiobook
                          </button>
                        )
                      ) : chase.audiobook_available === false ? (
                        <span className="muted">
                          {chase.audiobook_error
                            ? `Audiobook: ${chase.audiobook_error}`
                            : "No audiobook hit"}
                        </span>
                      ) : null}
                    </div>
                  ) : null}
                  {chase?.trace ? (
                    <details className="bestsellers-chase-trace" data-testid="bestsellers-chase-trace">
                      <summary>
                        Chase details
                        {chaseTraceSummary(chase) ? (
                          <span className="muted"> — {chaseTraceSummary(chase)}</span>
                        ) : null}
                      </summary>
                      <div className="bestsellers-chase-trace-body">
                        {chaseConversationLines(chase).length ? (
                          <section>
                            <p className="kicker">Conversation</p>
                            <ol className="bestsellers-chase-log">
                              {chaseConversationLines(chase).map((row, index) => (
                                <li key={`${row.role}-${index}`}>
                                  <span className="muted">{row.role}</span> {row.content}
                                </li>
                              ))}
                            </ol>
                          </section>
                        ) : null}
                        {chaseStepLines(chase).length ? (
                          <section>
                            <p className="kicker">Queries / steps</p>
                            <ol className="bestsellers-chase-log">
                              {chaseStepLines(chase).map((row, index) => (
                                <li key={`${row.lane}-${row.step}-${index}`}>
                                  <span className="muted">
                                    {row.lane} · {row.step}
                                  </span>{" "}
                                  {row.detail}
                                </li>
                              ))}
                            </ol>
                          </section>
                        ) : null}
                        {chaseResultRows(chase).length ? (
                          <section>
                            <p className="kicker">Result set</p>
                            <ol className="bestsellers-chase-log" data-testid="bestsellers-chase-results">
                              {chaseResultRows(chase).map((row, index) => (
                                <li key={`${row.lane}-${row.guid || row.title}-${index}`}>
                                  <strong>{row.decision}</strong>
                                  {row.reason ? ` — ${row.reason}` : ""} · {row.lane} · {row.title}
                                  {row.guid ? ` · ${row.guid}` : ""}
                                  {row.kind ? ` · ${row.kind}` : ""}
                                  {row.host ? ` · ${row.host}` : ""}
                                  {row.notes.length ? ` · ${row.notes.join("; ")}` : ""}
                                </li>
                              ))}
                            </ol>
                          </section>
                        ) : (
                          <p className="muted">No indexer rows returned for this title.</p>
                        )}
                        {chaseCandidateRows(chase).length ? (
                          <section>
                            <p className="kicker">Remembered alternates</p>
                            <ol className="bestsellers-chase-log" data-testid="bestsellers-chase-candidates">
                              {chaseCandidateRows(chase).map((row, index) => (
                                <li key={`${row.lane}-${row.guid}-${index}`}>
                                  {row.rank ? `#${row.rank} ` : ""}
                                  {row.lane} · {row.title} · {row.guid}
                                  {row.note ? ` · ${row.note}` : ""}
                                  {row.method ? ` · ${row.method}` : ""}
                                </li>
                              ))}
                            </ol>
                          </section>
                        ) : null}
                      </div>
                    </details>
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
