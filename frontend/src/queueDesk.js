/** Downloads desk views and bulk-dismiss helpers (PRD-011 / UX-005). */

export const QUEUE_VIEWS = ["actionable", "active", "history", "all"];

export const QUEUE_VIEW_ACTIONABLE = new Set(["asked", "failed", "review"]);
export const QUEUE_VIEW_ACTIVE = new Set(["queued", "downloading", "extracting", "identifying"]);
export const QUEUE_VIEW_HISTORY = new Set(["organized"]);
/** Individual dismiss (row button) — includes Asked. Active / Needs you stay blocked server-side. */
export const QUEUE_DISMISSIBLE = new Set(["asked", "failed", "skipped", "organized"]);

/** Bulk dismiss — Arrived / Failed only (PRD-011). Asked stays a per-row decision. */
export const QUEUE_BULK_DISMISSIBLE = new Set(["failed", "skipped", "organized"]);

export const DEFAULT_QUEUE_VIEW = "actionable";

export function normalizeQueueView(view) {
  const key = String(view || "").trim().toLowerCase();
  return QUEUE_VIEWS.includes(key) ? key : DEFAULT_QUEUE_VIEW;
}

export function queueViewLabel(view) {
  const key = normalizeQueueView(view);
  if (key === "active") return "Active";
  if (key === "history") return "History";
  if (key === "all") return "All jobs";
  return "Needs decision";
}

export function emptyQueueViewCopy(view) {
  const key = normalizeQueueView(view);
  if (key === "active") return "Nothing on the way right now.";
  if (key === "history") return "No arrived jobs in history.";
  if (key === "all") {
    return "Nothing in flight. Living chips live on Find cards; this list is for asked slips, SAB jobs, and volumes being filed.";
  }
  return "Nothing needs a decision. Active and History are one tap away.";
}

/** Terminal rows safe for bulk dismiss — never Asked, active, or Needs you. */
export function isQueueBulkDismissible(job) {
  return QUEUE_BULK_DISMISSIBLE.has(String(job?.status || ""));
}

export function dismissibleQueueJobs(jobs = []) {
  return (jobs || []).filter(isQueueBulkDismissible);
}

export function bulkDismissConfirmCopy(jobsOrCount = 0) {
  const list = Array.isArray(jobsOrCount) ? jobsOrCount : null;
  const n = list ? list.length : Number(jobsOrCount) || 0;
  const statuses = new Set((list || []).map((job) => String(job?.status || "")));
  const parts = [];
  if (statuses.has("organized")) parts.push("Arrived");
  if (statuses.has("failed") || statuses.has("skipped")) parts.push("Failed");
  const scope = parts.length ? parts.join(" / ") : "terminal";
  const noun = n === 1 ? "job" : "jobs";
  return {
    title: n === 1 ? "Dismiss 1 job?" : `Dismiss ${n} jobs?`,
    body:
      `This clears ${n} ${scope} ${noun} from Downloads. ` +
      "Asked slips, active transfers, and Needs you stay put. Dismissed rows move to skipped — open All jobs if you need them again.",
    confirmLabel: n === 1 ? "Dismiss 1 job" : `Dismiss ${n} jobs`,
    undoReminder: "There is no Safe undo for dismissed queue jobs — only skipped history under All jobs.",
  };
}

export function queueCounts(counts = {}) {
  return {
    actionable: Number(counts.actionable) || 0,
    active: Number(counts.active) || 0,
    history: Number(counts.history) || 0,
    all: Number(counts.all) || 0,
  };
}
