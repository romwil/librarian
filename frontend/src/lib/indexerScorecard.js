/** Indexer scorecard — lantern weather plus compact match-rate chips. */

export const LANTERN_ORDER = ["bright", "dim", "dark", "muted", "idle"];

export const HOUSEHOLD_KIND_ORDER = ["book", "magazine", "comic", "audiobook", "music"];

export const KIND_LABELS = {
  book: "Books",
  magazine: "Magazines",
  comic: "Comics",
  audiobook: "Audiobooks",
  music: "Music",
  "": "Any",
};

export function lanternWeather(row) {
  const weather = String(row?.weather || "").trim();
  if (LANTERN_ORDER.includes(weather)) return weather;
  if (row?.muted) return "muted";
  return "idle";
}

export function lanternPresence(row) {
  const fromServer = String(row?.presence || "").trim();
  if (fromServer) return fromServer;
  const weather = lanternWeather(row);
  const name = String(row?.name || "This host").trim() || "This host";
  if (weather === "muted") return `${name} rests muted — Find skips it until you unmute.`;
  if (weather === "dark") return `${name} went dark on the last Find.`;
  if (weather === "dim") return `${name} flickers — empty pages or a soft rate limit.`;
  if (weather === "bright") return `${name} burns steady.`;
  return `${name} has not spoken yet.`;
}

export function scorecardPresence(card) {
  const fromServer = String(card?.presence || "").trim();
  if (fromServer) return fromServer;
  return "Lanterns wait for the next Find beyond the shelves.";
}

export function scorecardLanterns(card) {
  return Array.isArray(card?.lanterns) ? card.lanterns : [];
}

export function kindStatLabel(kind) {
  const key = String(kind || "").trim().toLowerCase();
  if (Object.prototype.hasOwnProperty.call(KIND_LABELS, key)) return KIND_LABELS[key];
  return KIND_LABELS[""];
}

export function formatMatchPercent(rate) {
  if (rate == null || rate === "") return "—";
  const n = Number(rate);
  if (!Number.isFinite(n) || n < 0) return "—";
  return `${Math.round(Math.min(1, n) * 100)}%`;
}

function asCount(value) {
  const n = Number(value);
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0;
}

export function lanternKindBars(row, { showExtra = false } = {}) {
  void showExtra;
  const allowed = new Set(HOUSEHOLD_KIND_ORDER);
  allowed.add("");
  const raw = Array.isArray(row?.stats?.by_kind) ? row.stats.by_kind : [];
  const bars = [];
  for (const item of raw) {
    if (!item || typeof item !== "object") continue;
    const kind = String(item.kind || "").trim().toLowerCase();
    if (!allowed.has(kind)) continue;
    const searches = asCount(item.searches);
    if (searches < 1) continue;
    const hits = asCount(item.hits);
    const empty = asCount(item.empty);
    const spoken = hits + empty;
    const rate = spoken > 0 ? hits / spoken : null;
    bars.push({
      kind,
      label: kindStatLabel(kind),
      searches,
      hits,
      empty,
      errors: asCount(item.errors),
      rateLimited: asCount(item.rate_limited),
      matchRate: rate,
      percent: formatMatchPercent(rate),
      fill: rate == null ? 0 : Math.round(Math.min(1, Math.max(0, rate)) * 100),
    });
  }
  return bars;
}

export function lanternStatsModel(row, { showExtra = false } = {}) {
  const stats = row?.stats && typeof row.stats === "object" ? row.stats : null;
  const searches = asCount(stats?.searches);
  if (!stats || searches < 1) return null;
  const hits = asCount(stats.hits);
  const empty = asCount(stats.empty);
  const errors = asCount(stats.errors);
  const rateLimited = asCount(stats.rate_limited);
  const spoken = hits + empty;
  const rate = spoken > 0 ? hits / spoken : null;
  const notes = [];
  if (empty > 0) notes.push(`${empty} empty`);
  if (rateLimited > 0) notes.push(`${rateLimited} rate limit${rateLimited === 1 ? "" : "s"}`);
  else if (errors > 0) notes.push(`${errors} dark`);
  return {
    searches,
    hits,
    empty,
    errors,
    rateLimited,
    spoken,
    matchRate: rate,
    percent: formatMatchPercent(rate),
    spokenLabel: spoken === 1 ? "1 spoken" : `${spoken} spoken`,
    notes: notes.join(" · "),
    kinds: lanternKindBars(row, { showExtra }),
    lastSpokenAt: String(stats.last_spoken_at || "").trim(),
  };
}
