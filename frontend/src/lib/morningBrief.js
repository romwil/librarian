/** Morning desk voice helpers — keep copy warm, never KPI. */

const COUNT_WORDS = { 1: "one", 2: "two", 3: "three" };

/** Soft presence line from item count — never a scoreboard. */
export function morningTendPresence(count = 0) {
  const n = Math.max(0, Number(count) || 0);
  if (n < 1) return "The shelves are quiet this morning.";
  if (n === 1) return "Tend this one.";
  const word = COUNT_WORDS[n];
  if (word) return `Tend these ${word}.`;
  return "Tend these few.";
}

/** Prefer server presence; fall back so empty/hostile payloads stay warm. */
export function briefPresence(brief) {
  const fromServer = String(brief?.presence || "").trim();
  if (fromServer) return fromServer;
  const items = Array.isArray(brief?.items) ? brief.items : [];
  return morningTendPresence(items.length);
}

export function briefIsEmpty(brief) {
  if (!brief) return true;
  if (brief.empty === true) return true;
  const items = Array.isArray(brief.items) ? brief.items : [];
  return items.length < 1;
}

/** Rank kinds for unit proofs — mirrors librarian.morning_brief._SIGNAL_ORDER. */
export const MORNING_SIGNAL_ORDER = [
  "shelf_health",
  "holds_desk",
  "extra_files",
  "unshelved_shells",
  "comic_book_blends",
];

export function rankMorningKinds(signals = {}) {
  const picked = [];
  for (const kind of MORNING_SIGNAL_ORDER) {
    const n = Math.max(0, Number(signals[kind]) || 0);
    if (n < 1) continue;
    picked.push(kind);
    if (picked.length >= 3) break;
  }
  return picked;
}
