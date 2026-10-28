import { findHref, searchHref } from "./find.js";
import { workListenPath } from "./listen.js";
import { workDownloadUrl, workReaderPath } from "./reader.js";

function text(value) {
  return String(value || "").trim();
}

export function notedQuery(item = {}, bag = {}) {
  return {
    q: text(bag.q),
    kind: text(bag.kind || item.kind),
    title: text(bag.title || item.title),
    author: text(bag.author || item.author),
    isbn: text(bag.isbn || item.isbn),
  };
}

export function notedSearchHref(item = {}) {
  return searchHref(notedQuery(item, item.search || {}));
}

export function notedFindHref(item = {}) {
  return findHref(notedQuery(item, item.find || {}));
}

export function notedWantedBody(item = {}, kind) {
  const wanted = item.wanted || {};
  return {
    title: text(wanted.title || item.title),
    author: text(wanted.author || item.author),
    isbn: text(wanted.isbn || item.isbn),
    kind: text(kind || wanted.kind || item.kind || "book"),
  };
}

function ownedStub(stub) {
  const id = text(stub?.id);
  if (!id) return null;
  return { id, href: `/works/${encodeURIComponent(id)}` };
}

/** Book and audiobook actions for one noted card. Owned formats link to the shelf. */
export function notedFormatActions(item = {}) {
  const book = ownedStub(item.shelved);
  const audio = ownedStub(item.shelved_audiobook);
  return ["book", "audiobook"].map((kind) => {
    const owned = kind === "audiobook" ? audio : book;
    if (owned) {
      const book = kind === "book";
      return {
        kind,
        owned: true,
        label: "On the shelf",
        href: owned.href,
        listenHref: kind === "audiobook" ? workListenPath(owned.id) : "",
        readHref: book ? workReaderPath(owned.id) : "",
        downloadHref: book ? workDownloadUrl(owned.id) : "",
      };
    }
    return {
      kind,
      owned: false,
      label: `Add to Wanted · ${kind}`,
      href: "",
      listenHref: "",
      readHref: "",
      downloadHref: "",
    };
  });
}

/** List cards speak for the title's own format. The other format stays on the work page. */
export function listFormatActions(item = {}) {
  const kind = text(item.kind) || "book";
  return notedFormatActions(item).filter((action) => action.kind === kind);
}

function norm(value) {
  return String(value || "")
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toLowerCase()
    .replace(/&/g, " and ")
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** ISBN-13 only. A 10-digit value falls through to title and author. */
export function notedIsbn13(item = {}) {
  const raw = String(item?.isbn13 || item?.isbn || "").replace(/[^0-9]/g, "");
  return raw.length === 13 ? raw : "";
}

function titleAuthorKey(item = {}) {
  const title = norm(item.title);
  if (!title) return "";
  return `${title}|${norm(item.author)}`;
}

/** Shelf, already wanted, or still missing. A shelved stub counts as on the shelf. */
export function notedBookStatus(item = {}) {
  if (item?.status === "matched" || item?.shelved === true || ownedStub(item?.shelved)) return "matched";
  if (item?.status === "wanted" || item?.wanted === true) return "wanted";
  return "missing";
}

const STATUS_RANK = { matched: 3, wanted: 2, missing: 1 };

export function notedWorkHref(item = {}) {
  const id = text(ownedStub(item?.shelved)?.id) || text(item?.work_id);
  return id ? `/works/${encodeURIComponent(id)}` : "";
}

function weekCountOf(group) {
  const dates = new Set();
  let numeric = 0;
  let sawDates = false;
  let sawNumeric = false;
  for (const item of group) {
    if (Array.isArray(item?.weeks)) {
      sawDates = true;
      for (const week of item.weeks) {
        const value = text(week);
        if (value) dates.add(value);
      }
    } else if (typeof item?.weeks === "number" && Number.isFinite(item.weeks)) {
      sawNumeric = true;
      numeric = Math.max(numeric, item.weeks);
    } else if (typeof item?.weekCount === "number" && Number.isFinite(item.weekCount)) {
      sawNumeric = true;
      numeric = Math.max(numeric, item.weekCount);
    }
  }
  if (sawDates) return dates.size;
  return sawNumeric ? numeric : 0;
}

/** "6 weeks" when the range already knows a count above one. Dates stay off the card. */
export function weekCountLabel(count) {
  const n = Number(count);
  if (!Number.isFinite(n) || n < 2) return "";
  return `${Math.trunc(n)} weeks`;
}

function mergeNotedBooks(group) {
  const ranked = [...group].sort((a, b) => STATUS_RANK[notedBookStatus(b)] - STATUS_RANK[notedBookStatus(a)]);
  const primary = group[0] || {};
  const best = ranked[0] || primary;
  const isbn = group.map(notedIsbn13).find(Boolean) || "";
  const stub = group.map((item) => ownedStub(item.shelved)).find(Boolean) || null;
  const audio = group.map((item) => ownedStub(item.shelved_audiobook)).find(Boolean) || null;
  const workId = text(stub?.id) || group.map((item) => text(item.work_id)).find(Boolean) || "";
  const status = notedBookStatus(best);
  const kind = group.some((item) => (text(item.kind) || "book") === "book")
    ? "book"
    : text(group.find((item) => text(item.kind))?.kind) || "book";
  const book = {
    ...primary,
    title: group.map((item) => text(item.title)).find(Boolean) || "",
    author: group.map((item) => text(item.author)).find(Boolean) || "",
    isbn,
    isbn13: isbn,
    kind,
    work_id: workId,
    shelved: stub || group.some((item) => item.shelved === true),
    shelved_audiobook: audio,
    wanted: group.some((item) => item.wanted === true) ? true : best.wanted,
    status,
    weekCount: weekCountOf(group),
  };
  delete book.weeks;
  const identity = notedIsbn13(book) ? `isbn:${notedIsbn13(book)}` : titleAuthorKey(book);
  book.key = identity || `row:${text(primary.source_key) || text(primary.id) || `${text(primary.rank)}:${text(primary.published_date)}`}`;
  return book;
}

/**
 * One card per book. Same ISBN-13 collapses first; the same normalized title
 * and author also collapse, including rows that carry different ISBNs or none.
 */
export function collapseNotedBooks(items = []) {
  const list = (Array.isArray(items) ? items : []).filter((item) => item && typeof item === "object");
  const parent = list.map((_, index) => index);
  const find = (index) => {
    let cursor = index;
    while (parent[cursor] !== cursor) {
      parent[cursor] = parent[parent[cursor]];
      cursor = parent[cursor];
    }
    return cursor;
  };
  const union = (keep, extra) => {
    const left = find(keep);
    const right = find(extra);
    if (left !== right) parent[right] = left;
  };
  const byIsbn = new Map();
  const byTitle = new Map();
  list.forEach((item, index) => {
    const isbn = notedIsbn13(item);
    if (isbn) {
      const prior = byIsbn.get(isbn);
      if (prior == null) byIsbn.set(isbn, index);
      else union(prior, index);
    }
    const key = titleAuthorKey(item);
    if (key) {
      const prior = byTitle.get(key);
      if (prior == null) byTitle.set(key, index);
      else union(prior, index);
    }
  });
  const groups = new Map();
  list.forEach((item, index) => {
    const root = find(index);
    const group = groups.get(root);
    if (group) group.push(item);
    else groups.set(root, [item]);
  });
  return [...groups.values()].map(mergeNotedBooks);
}
