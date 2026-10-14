/** Wanted desk rows: companion misses and hand-added titles. Not the Holds desk. */

import { canManageWanted } from "./availability.js";
import { workListenPath } from "./listen.js";

function trimmed(value) {
  return String(value || "").trim();
}

const KIND_PLURAL = {
  book: "books",
  audiobook: "audiobooks",
  magazine: "magazines",
  comic: "comics",
  music: "music",
};

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

export function wantedRetryLine(nextSearchAt, nowSeconds = Date.now() / 1000) {
  const at = Number(nextSearchAt || 0);
  const now = Number(nowSeconds || 0);
  if (!at || at <= now) return "";
  const seconds = at - now;
  const hours = Math.round(seconds / 3600);
  if (hours < 1) return "Tries again in under an hour.";
  if (hours < 48) return `Tries again in ${hours} hour${hours === 1 ? "" : "s"}.`;
  const days = Math.round(hours / 24);
  return `Tries again in ${days} day${days === 1 ? "" : "s"}.`;
}

export function wantedSearchStatus(item = {}, { searching = false, attempt = null, now = Date.now() / 1000 } = {}) {
  if (searching) {
    return { label: "Searching", detail: "", retry: "" };
  }
  const status = trimmed(item.status) || "wanted";
  const retry = status === "wanted" ? wantedRetryLine(item.next_search_at, now) : "";
  if (attempt?.downloader) {
    return {
      label: status === "asked" ? "Asked" : "Wanted",
      detail: "The downloader did not answer.",
      retry,
    };
  }
  if (attempt?.outcome === "already_asked" || status === "asked") {
    const detail = attempt?.outcome === "already_asked" ? "Already on a slip." : "On a slip, waiting for confirm.";
    return { label: "Asked", detail: attempt?.detail || detail, retry: "" };
  }
  if (attempt?.outcome === "miss") {
    return { label: "Wanted", detail: "Nothing found.", retry };
  }
  if (attempt?.outcome === "hit") {
    return { label: "Asked", detail: "A hit is on a slip.", retry: "" };
  }
  return { label: "Wanted", detail: "Waiting for the next search.", retry };
}

export function wantedSearchAllLabel(kind = "") {
  const key = trimmed(kind).toLowerCase();
  if (!key || key === "all") return "Search all";
  return `Search all ${KIND_PLURAL[key] || key}`;
}

export function wantedToolbarModel({ kind = "", selectedCount = 0, role = "reader", total = 0 } = {}) {
  const canSearch = canManageWanted(role);
  return {
    canSearch,
    selectPageLabel: "Select page",
    searchSelectedLabel: "Search selected",
    searchAllLabel: wantedSearchAllLabel(kind),
    searchSelectedDisabled: !canSearch || selectedCount < 1,
    searchAllDisabled: !canSearch || total < 1,
  };
}

export function wantedRowModel(item = {}, role = "reader", extras = {}) {
  const kind = trimmed(item.kind) || "audiobook";
  const title = trimmed(item.title) || "Untitled";
  const author = trimmed(item.author);
  const isbn = trimmed(item.isbn);
  const status = trimmed(item.status) || "wanted";
  const search = wantedSearchStatus(item, extras);
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
    statusLabel: search.label,
    statusDetail: search.detail,
    retryLine: search.retry,
    workId: trimmed(item.work_id),
    jobId: trimmed(item.job_id),
    nextSearchAt: item.next_search_at,
    canDismiss: canManageWanted(role) && Boolean(trimmed(item.id)) && status !== "dismissed",
    bookShelf,
    audioShelf,
  };
}

export function wantedDeskModel({
  items = [],
  role = "reader",
  attempts = {},
  inflight = {},
  kind = "",
  selectedCount = 0,
  total = 0,
} = {}) {
  const rows = (Array.isArray(items) ? items : [])
    .filter((item) => item && item.status !== "dismissed")
    .map((item) =>
      wantedRowModel(item, role, {
        searching: Boolean(inflight[item.id]),
        attempt: attempts[item.id] || null,
      }),
    );
  return {
    rows,
    canAdd: canManageWanted(role),
    canSearch: canManageWanted(role),
    empty: rows.length === 0,
    toolbar: wantedToolbarModel({ kind, selectedCount, role, total: total || rows.length }),
  };
}
