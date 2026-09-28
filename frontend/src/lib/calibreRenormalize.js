/** Calibre re-normalize — one graceful ritual. */

export function renormalizeIsAvailable(preview) {
  return Boolean(preview?.available);
}

export function renormalizeReadyCount(preview) {
  const n = Number(preview?.counts?.copy || 0);
  return Number.isFinite(n) && n > 0 ? n : 0;
}

export function renormalizePresence(preview) {
  const fromServer = String(preview?.presence || "").trim();
  if (fromServer) return fromServer;
  if (!renormalizeIsAvailable(preview)) {
    return "No Calibre dump is waiting near the books root.";
  }
  return "Look first — the lamp maps the dump before anything moves.";
}
