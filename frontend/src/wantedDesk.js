/** Wanted desk rows: companion misses and hand-added titles. Not the Holds desk. */

import { findHref, searchHref } from "./find.js";
import { canManageWanted } from "./availability.js";

function trimmed(value) {
  return String(value || "").trim();
}

export function wantedRowModel(item = {}, role = "reader") {
  const kind = trimmed(item.kind) || "audiobook";
  const title = trimmed(item.title) || "Untitled";
  const author = trimmed(item.author);
  const isbn = trimmed(item.isbn);
  const fields = { kind, title, author, isbn };
  const status = trimmed(item.status) || "wanted";
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
