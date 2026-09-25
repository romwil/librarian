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
  if (kind === "arrived" && payload.work_id) return `/works/${encodeURIComponent(payload.work_id)}`;
  if (kind === "someone_finished" && payload.work_id) return `/works/${encodeURIComponent(payload.work_id)}`;
  return null;
}

export function normalizeTiming(value) {
  const raw = String(value || "realtime").trim().toLowerCase();
  if (raw === "daily" || raw === "weekly") return raw;
  return "realtime";
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
