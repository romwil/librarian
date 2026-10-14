/** Wanted desk rows: companion misses and hand-added titles. Not the Holds desk. */

import { findHref, searchHref } from "./find.js";
import { canManageWanted } from "./availability.js";
import { workListenPath } from "./listen.js";

function trimmed(value) {
  return String(value || "").trim();
}

function shelfLink(stub, label) {
  const id = trimmed(stub?.id);
  if (!id) return null;
  return {
    id,
    href: `/works/${encodeURIComponent(id)}`,
    label,
    listenHref: workListenPath(id),
  };
}

export function wantedRowModel(item = {}, role = "reader") {
  const kind = trimmed(item.kind) || "audiobook";
  const title = trimmed(item.title) || "Untitled";
  const author = trimmed(item.author);
  const isbn = trimmed(item.isbn);
  const fields = { kind, title, author, isbn };
  const status = trimmed(item.status) || "wanted";
  const bookShelf = shelfLink(item.shelved_book, kind === "book" ? "On the shelf" : "Book on the shelf");
  const audioShelf = shelfLink(
    item.shelved_audiobook,
    kind === "audiobook" ? "On the shelf" : "Audiobook on the shelf",
  );
  return {
    id: trimmed(item.id),
    title,
    author,
    kind,
    isbn,
    status,
    statusLabel: status === "asked" ? "Asked" : "Wanted",
    workId: trimmed(item.work_id),
    searchHref: searchHref(fields),
    findHref: findHref(fields),
    canDismiss: canManageWanted(role) && Boolean(trimmed(item.id)) && status !== "dismissed",
    bookShelf,
    audioShelf,
  };
}

export function wantedDeskModel({ items = [], role = "reader" } = {}) {
  const rows = (Array.isArray(items) ? items : [])
    .filter((item) => item && item.status !== "dismissed")
    .map((item) => wantedRowModel(item, role));
  return {
    rows,
    canAdd: canManageWanted(role),
    empty: rows.length === 0,
  };
}
