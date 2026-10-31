/** Wanted desk rows: companion misses and hand-added titles. Not the Holds desk. */

import { canManageWanted } from "./availability.js";
import { workListenPath } from "./listen.js";

/** Local Wanted strings so this sprint does not edit copy.js. */
export const WANTED_COPY = {
  sourceSweep: "Sweep",
  sourceOwner: "Owner want",
  dismissSweep: "Dismiss sweep wants",
  restore: "Restore",
  restoreSweep: "Restore recent sweep wants",
  open: "Open",
  recentlyDismissed: "Restorable",
  sweepOn: "Automatic audiobook wants: on",
  sweepOff: "Automatic audiobook wants: off",
  turnSweepOn: "Turn automatic audiobook wants on",
  turnSweepOff: "Turn automatic audiobook wants off",
};

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
  if (status === "arrived") {
    return { label: "On the shelf", detail: "Filed on the shelves.", retry: "" };
  }
  if (attempt?.outcome === "already_asked" || status === "asked") {
    const detail = attempt?.outcome === "already_asked" ? "Already on a slip." : "On a slip, waiting for confirm.";
    return { label: "Asked", detail: attempt?.detail || detail, retry: "" };
  }
  if (attempt?.outcome === "miss") {
    return { label: "Wanted", detail: "Nothing found.", retry };
  }
  if (attempt?.outcome === "rate_limited") {
    return { label: "Wanted", detail: "The indexer asked us to wait. The next hourly pass tries again.", retry };
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

export function wantedSourceLabel(source = "") {
  return trimmed(source).toLowerCase() === "manual" ? WANTED_COPY.sourceOwner : WANTED_COPY.sourceSweep;
}

export function wantedToolbarModel({
  kind = "",
  selectedCount = 0,
  role = "reader",
  total = 0,
  sweepOpen = 0,
  restorable = 0,
  viewingDismissed = false,
} = {}) {
  const canSearch = canManageWanted(role);
  const canManage = canManageWanted(role);
  return {
    canSearch,
    selectPageLabel: "Select page",
    searchSelectedLabel: "Search selected",
    searchAllLabel: wantedSearchAllLabel(kind),
    searchSelectedDisabled: !canSearch || selectedCount < 1 || viewingDismissed,
    searchAllDisabled: !canSearch || total < 1 || viewingDismissed,
    dismissSweepLabel: WANTED_COPY.dismissSweep,
    dismissSweepDisabled: !canManage || viewingDismissed || Number(sweepOpen) < 1,
    restoreSweepLabel: WANTED_COPY.restoreSweep,
    restoreSweepDisabled: !canManage || Number(restorable) < 1,
  };
}

export function wantedRowModel(item = {}, role = "reader", extras = {}) {
  const kind = trimmed(item.kind) || "audiobook";
  const title = trimmed(item.title) || "Untitled";
  const author = trimmed(item.author);
  const isbn = trimmed(item.isbn);
  const status = trimmed(item.status) || "wanted";
  const source = trimmed(item.source).toLowerCase() === "manual" ? "manual" : "sweep";
  const search = wantedSearchStatus(item, extras);
  const bookShelf = shelfLink(item.shelved_book, kind === "book" ? "On the shelf" : "Book on the shelf");
  const audioShelf = shelfLink(
    item.shelved_audiobook,
    kind === "audiobook" ? "On the shelf" : "Audiobook on the shelf",
  );
  const canManage = canManageWanted(role);
  return {
    id: trimmed(item.id),
    title,
    author,
    kind,
    isbn,
    status,
    source,
    sourceLabel: wantedSourceLabel(source),
    statusLabel: search.label,
    statusDetail: search.detail,
    retryLine: search.retry,
    workId: trimmed(item.work_id),
    jobId: trimmed(item.job_id),
    nextSearchAt: item.next_search_at,
    canSearchRow: canManage && status === "wanted",
    canFindBeyond: canManage && status !== "arrived" && status !== "dismissed",
    canDismiss: canManage && Boolean(trimmed(item.id)) && status !== "dismissed" && status !== "arrived",
    canRestore: canManage && Boolean(trimmed(item.id)) && status === "dismissed" && Boolean(item.restorable),
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
  includeDismissed = false,
  sweep = {},
} = {}) {
  const rows = (Array.isArray(items) ? items : [])
    .filter((item) => item && (includeDismissed || item.status !== "dismissed"))
    .map((item) =>
      wantedRowModel(item, role, {
        searching: Boolean(inflight[item.id]),
        attempt: attempts[item.id] || null,
      }),
    );
  const sweepOpen = Number(sweep.open || 0);
  const restorable = Number(sweep.restorable || 0);
  return {
    rows,
    canAdd: canManageWanted(role),
    canSearch: canManageWanted(role),
    canToggleSweep: role === "owner",
    empty: rows.length === 0,
    sweepEnabled: Boolean(sweep.enabled),
    sweepOpen,
    sweepCap: Number(sweep.cap || 0),
    restorable,
    toolbar: wantedToolbarModel({
      kind,
      selectedCount,
      role,
      total: total || rows.length,
      sweepOpen,
      restorable,
      viewingDismissed: includeDismissed,
    }),
  };
}
