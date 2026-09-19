/** Shared busy / note labels for long Review and Settings actions. */

export const ACTION_BUSY_LABELS = {
  apply: "Applying…",
  skip: "Skipping…",
  retry: "Retrying…",
  repair: "Repairing…",
  suggest: "Suggesting…",
  regrab: "Looking for releases…",
  request: "Requesting…",
  enrich: "Enriching…",
  scan: "Scanning…",
  save: "Saving…",
  match: "Matching…",
  clear: "Clearing…",
};

export const ACTION_DONE_LABELS = {
  apply: "Applied.",
  skip: "Skipped.",
  retry: "Retry queued.",
  repair: "Repair started.",
  suggest: "Suggested — confirm the fields, then Apply.",
  regrab: "Releases ready.",
  request: "Requested.",
  enrich: "Enrich finished.",
  scan: "Scan finished.",
  save: "Saved.",
};

export function busyLabel(action, { fallback = "Working…" } = {}) {
  const key = String(action || "").trim();
  return ACTION_BUSY_LABELS[key] || fallback;
}

export function doneLabel(action, { fallback = "Done." } = {}) {
  const key = String(action || "").trim();
  return ACTION_DONE_LABELS[key] || fallback;
}

/** True when this ticket (or page) is mid-flight for any action. */
export function isBusy(busyMap, id) {
  return Boolean(busyMap && busyMap[id]);
}

/** Active action key for a ticket, or "". */
export function busyAction(busyMap, id) {
  const value = busyMap?.[id];
  if (!value) return "";
  return typeof value === "string" ? value : "working";
}

export function ticketStatusNote(busyMap, notes, id) {
  const action = busyAction(busyMap, id);
  if (action) return busyLabel(action);
  return String(notes?.[id] || "");
}

export function enrichProgressSummary(status) {
  if (!status || typeof status !== "object") return "";
  const state = String(status.status || "");
  if (state === "idle") return "";
  if (state === "failed") return status.error || "Enrich failed.";
  const done = Number(status.done || 0);
  const total = Number(status.total || 0);
  const updated = Number(status.updated || 0);
  const title = String(status.current_title || "").trim();
  if (state === "completed") {
    const result = status.result || {};
    const scanned = Number(result.scanned != null ? result.scanned : done);
    const filled = Number(result.updated != null ? result.updated : updated);
    return `Enriched ${filled} of ${scanned} thin volumes`;
  }
  if (total > 0) {
    const head = title ? ` · ${title}` : "";
    return `${done} of ${total}${head}`;
  }
  if (title) return title;
  return state === "running" ? "Enriching…" : "";
}

export function enrichIsRunning(status) {
  return String(status?.status || "") === "running";
}
