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
  const skipped = Number(status.skipped || 0);
  const errors = Number(status.errors || 0);
  const title = String(status.current_title || "").trim();
  if (state === "completed") {
    const result = status.result || {};
    const scanned = Number(result.scanned != null ? result.scanned : done);
    const filled = Number(result.updated != null ? result.updated : updated);
    const skip = Number(result.skipped != null ? result.skipped : skipped);
    const failed = Number(result.errors != null ? result.errors : errors);
    const parts = [`Enriched ${filled} of ${scanned} thin volumes`];
    if (skip) parts.push(`${skip} skipped`);
    if (failed) parts.push(`${failed} failed`);
    return parts.join(" · ");
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

export function enrichPhaseLabel(phase) {
  const key = String(phase || "").trim();
  if (key === "starting") return "starting";
  if (key === "enriching") return "enriching";
  if (key === "trickle") return "trickle";
  if (key === "done") return "done";
  if (key === "failed") return "failed";
  return key || "enrich";
}

export function scanProgressSummary(status) {
  if (!status || typeof status !== "object") return "";
  const state = String(status.status || "");
  if (state === "idle") return "";
  if (state === "failed") return status.error || "Scan failed.";
  const done = Number(status.done || 0);
  const total = Number(status.total || 0);
  const created = Number(status.created || 0);
  const updated = Number(status.updated || 0);
  const review = Number(status.review || 0);
  const errors = Number(status.errors || 0);
  const title = String(status.current_title || "").trim();
  if (state === "completed") {
    const result = status.result || {};
    const scanned = Number(result.scanned != null ? result.scanned : done);
    const neu = Number(result.created != null ? result.created : created);
    const up = Number(result.updated != null ? result.updated : updated);
    const needs = Number(result.review != null ? result.review : review);
    const failed = Number(result.errors != null ? result.errors : errors);
    const parts = [`Scanned ${scanned}`, `${neu} new`, `${up} updated`];
    if (needs) parts.push(`${needs} need review`);
    if (failed) parts.push(`${failed} failed`);
    return parts.join(" · ");
  }
  if (total > 0) {
    const head = title ? ` · ${title}` : "";
    return `${done} of ${total}${head}`;
  }
  if (title) return title;
  return state === "running" ? "Scanning…" : "";
}

export function scanIsRunning(status) {
  return String(status?.status || "") === "running";
}

export function scanPhaseLabel(phase) {
  const key = String(phase || "").trim();
  if (key === "starting") return "starting";
  if (key === "listing") return "listing";
  if (key === "scanning") return "scanning";
  if (key === "done") return "done";
  if (key === "failed") return "failed";
  return key || "scan";
}
