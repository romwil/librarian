import { useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { api } from "../api.js";
import NotedBookCard from "../components/NotedBookCard.jsx";
import { Thinking, ThinkingButton } from "../components/Thinking.jsx";
import { humanError } from "../copy.js";
import { collapseNotedBooks, notedBookStatus, notedSearchHref, notedWorkHref, weekCountLabel } from "../noted.js";

const NYT_LISTS = [
  ["hardcover-fiction", "Hardcover Fiction"],
  ["hardcover-nonfiction", "Hardcover Nonfiction"],
  ["combined-print-and-e-book-fiction", "Combined Print & E-Book Fiction"],
  ["combined-print-and-e-book-nonfiction", "Combined Print & E-Book Nonfiction"],
  ["paperback-nonfiction", "Paperback Nonfiction"],
  ["young-adult-hardcover", "Young Adult Hardcover"],
  ["childrens-middle-grade-hardcover", "Children’s Middle Grade"],
];

const STATUS_WORD = {
  matched: "Matched",
  wanted: "Wanted",
  missing: "Missing",
};

function sixMonthsAgo() {
  const day = new Date();
  day.setMonth(day.getMonth() - 6);
  return day.toISOString().slice(0, 10);
}

function shelfQuery(book) {
  return {
    ...book,
    kind: book.kind || "book",
    isbn: book.isbn || book.isbn13 || "",
  };
}

export default function NotedHistoryPage() {
  const { user } = useOutletContext() || {};
  const [listName, setListName] = useState(NYT_LISTS[0][0]);
  const [start, setStart] = useState(sixMonthsAgo);
  const [end, setEnd] = useState(() => new Date().toISOString().slice(0, 10));
  const [history, setHistory] = useState(null);
  const [wantedKeys, setWantedKeys] = useState(() => new Set());
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");

  if (user?.role !== "owner") return null;

  const books = collapseNotedBooks(history?.items).map((book) => (
    wantedKeys.has(book.key) ? { ...book, status: "wanted", wanted: true } : book
  ));

  async function load() {
    setBusy("load");
    setNote("");
    setWantedKeys(new Set());
    try {
      setHistory(await api.notedHistory({ listName, start, end }));
    } catch (error) {
      setHistory(null);
      setNote(humanError(error));
    } finally {
      setBusy("");
    }
  }

  async function addMissing() {
    if (!history) return;
    setBusy("add");
    setNote("");
    try {
      const result = await api.addMissingNotedHistory(books);
      const added = Number(result?.added || 0);
      setNote(`Added ${added} missing title${added === 1 ? "" : "s"} to Wanted.`);
      setWantedKeys(new Set());
      setHistory(await api.notedHistory({ listName, start, end }));
    } catch (error) {
      setNote(humanError(error));
    } finally {
      setBusy("");
    }
  }

  async function addOne(book) {
    setBusy(book.key);
    setNote("");
    try {
      await api.addMissingNotedHistory([book]);
      setWantedKeys((current) => new Set(current).add(book.key));
    } catch (error) {
      setNote(humanError(error));
    } finally {
      setBusy("");
    }
  }

  return (
    <div className="admin-room page-settle" data-testid="noted-history-page">
      <p className="kicker">Owner</p>
      <h1>New &amp; noted history</h1>
      <p className="lede">Fetch a New York Times category once per week, then review the distinct titles from the selected range.</p>
      <div className="cta-row align-end">
        <label className="field">NYT category
          <select aria-label="NYT category" value={listName} onChange={(event) => setListName(event.target.value)}>
            {NYT_LISTS.map(([id, label]) => (
              <option key={id} value={id}>{label}</option>
            ))}
          </select>
        </label>
        <label className="field">Start
          <input aria-label="Start date" type="date" value={start} onChange={(event) => setStart(event.target.value)} />
        </label>
        <label className="field">End
          <input aria-label="End date" type="date" value={end} onChange={(event) => setEnd(event.target.value)} />
        </label>
        <ThinkingButton
          type="button"
          className="cta outline"
          busy={busy === "load"}
          disabled={Boolean(busy) && busy !== "load"}
          onClick={load}
        >
          Load range
        </ThinkingButton>
      </div>
      {busy ? <Thinking testId="noted-history-thinking" /> : null}
      {history?.origin_label ? (
        <p className="muted" data-testid="noted-history-origin">{history.origin_label}</p>
      ) : null}
      {history?.empty_copy ? <p className="muted">{history.empty_copy}</p> : null}
      {history ? (
        <>
          <div className="cta-row">
            <ThinkingButton
              type="button"
              className="cta"
              busy={busy === "add"}
              disabled={Boolean(busy) && busy !== "add"}
              onClick={addMissing}
            >
              Add missing
            </ThinkingButton>
          </div>
          <ul className="noted-books">
            {books.map((book) => {
              const status = notedBookStatus(book);
              const href = status === "matched" ? notedWorkHref(book) : "";
              return (
                <NotedBookCard
                  key={book.key}
                  book={book}
                  status={STATUS_WORD[status]}
                  weeks={weekCountLabel(book.weekCount)}
                >
                  <Link className="cta outline compact" to={notedSearchHref(shelfQuery(book))} data-testid="noted-search">
                    Search the shelves
                  </Link>
                  {href ? (
                    <Link className="cta compact" to={href} data-testid="noted-open">
                      Open
                    </Link>
                  ) : null}
                  {status === "missing" ? (
                    <ThinkingButton
                      type="button"
                      className="cta compact"
                      busy={busy === book.key}
                      disabled={Boolean(busy) && busy !== book.key}
                      data-testid="noted-want-book"
                      onClick={() => addOne(book)}
                    >
                      Add to Wanted
                    </ThinkingButton>
                  ) : null}
                </NotedBookCard>
              );
            })}
          </ul>
        </>
      ) : null}
      {note ? <p className="muted" role="status">{note}</p> : null}
    </div>
  );
}
