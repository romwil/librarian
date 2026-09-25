/**
 * Pure helpers for the Librarian notifications inbox.
 * Kinds: asked_confirm | arrived | needs_you | quiet_hours_wake |
 *        newsletter | someone_finished | shelf_health
 */

export const NOTIFICATION_KINDS = [
  "asked_confirm",
  "arrived",
  "needs_you",
  "quiet_hours_wake",
  "newsletter",
  "someone_finished",
  "shelf_health",
];

/** Inbox page fetch contract — unread only so dismiss stays sticky. */
export const INBOX_LIST_PARAMS = Object.freeze({ unread_only: true, limit: 50 });

export const KIND_LABELS = {
  asked_confirm: "Needs confirm",
  arrived: "Arrived",
  needs_you: "Needs you",
  quiet_hours_wake: "Quiet hours",
  newsletter: "Newsletter",
  someone_finished: "Finished",
  shelf_health: "Shelf health",
};

export const NEWSLETTER_TIMINGS = [
  { value: "weekly", label: "Weekly" },
  { value: "monthly", label: "Monthly" },
];

export const NEWSLETTER_SCOPES = [
  { value: "self", label: "Just me" },
  { value: "all", label: "Everyone opted in" },
];

export function formatUnreadBadge(count) {
  const n = Number(count) || 0;
  if (n <= 0) return "";
  if (n > 99) return "99+";
  return String(n);
}

export function inboxHeadline(items = []) {
  const list = Array.isArray(items) ? items : [];
  if (!list.length) return "Inbox";
  if (list.length === 1) {
    const kind = String(list[0]?.kind || "");
    if (kind === "arrived") return "Something arrived for you";
    if (kind === "needs_you") return "Review needs you";
    if (kind === "asked_confirm") return "A Request needs confirm";
    if (kind === "quiet_hours_wake") return "Quiet hours are over";
    if (kind === "newsletter") return "A letter from the library";
    if (kind === "someone_finished") return "Someone finished a title";
    if (kind === "shelf_health") return "Shelf health needs a tend";
    return "You have a notice";
  }
  return `${list.length} new notices`;
}

export function inboxCardCopy(item) {
  const kind = String(item?.kind || "");
  const eyebrow = KIND_LABELS[kind] || "Notice";
  const lead = String(item?.title || "").trim() || "Notice from the library";
  const note = String(item?.body || item?.message || "").trim() || null;
  return { eyebrow, lead, note, href: inboxItemHref(item) };
}

export function inboxItemHref(item) {
  const kind = String(item?.kind || "");
  const payload = item?.payload && typeof item.payload === "object" ? item.payload : {};
  if (payload.path && String(payload.path).startsWith("/")) return String(payload.path);
  if (kind === "needs_you" || kind === "asked_confirm") return "/review";
  if (kind === "shelf_health") return "/maintain";
  if (kind === "newsletter") return "/inbox";
  if (kind === "arrived" && payload.work_id) return `/works/${encodeURIComponent(payload.work_id)}`;
  if (kind === "someone_finished" && payload.work_id) return `/works/${encodeURIComponent(payload.work_id)}`;
  return null;
}

export function normalizeTiming(value) {
  const raw = String(value || "realtime").trim().toLowerCase();
  if (raw === "daily" || raw === "weekly" || raw === "monthly") return raw;
  return "realtime";
}

export function normalizeNewsletterTiming(value) {
  const raw = String(value || "weekly").trim().toLowerCase();
  if (raw === "monthly") return "monthly";
  return "weekly";
}

export function normalizeChannels(value) {
  const list = Array.isArray(value) ? value : [];
  const out = [];
  for (const entry of list) {
    const id = String(entry || "").trim().toLowerCase();
    if ((id === "inbox" || id === "email") && !out.includes(id)) out.push(id);
  }
  return out.length ? out : ["inbox"];
}

/**
 * @param {"self"|"all"} scope
 * @returns {string}
 */
export function newsletterConfirmMessage(scope) {
  if (scope === "self") {
    return "Send your library letter now? You need Library newsletter opted in — email only leaves if you turned that channel on.";
  }
  return "Send the library letter to everyone who opted in? Channel prefs (inbox / email) still apply — never force-email.";
}

/**
 * @param {{ delivered?: number, emailed?: number, skipped_opt_out?: number, skipped_not_due?: number }} result
 * @returns {string}
 */
export function newsletterResultMessage(result = {}) {
  const delivered = Number(result.delivered) || 0;
  const emailed = Number(result.emailed) || 0;
  const skipped = Number(result.skipped_opt_out) || 0;
  const notDue = Number(result.skipped_not_due) || 0;
  const parts = [`Delivered to ${delivered} inbox${delivered === 1 ? "" : "es"}`];
  if (emailed > 0) parts.push(`${emailed} emailed`);
  if (skipped > 0) parts.push(`${skipped} skipped (not opted in)`);
  if (notDue > 0) parts.push(`${notDue} not due yet`);
  return `${parts.join(" · ")}.`;
}
