/** Indexer scorecard — lantern weather, never a latency KPI strip. */

export const LANTERN_ORDER = ["bright", "dim", "dark", "muted", "idle"];

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
