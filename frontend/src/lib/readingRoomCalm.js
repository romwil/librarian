/** Reading room calm — margins, chrome dim, reduced-motion helpers. */

/** Idle ms before chrome dims; reduced-motion callers skip dimming. */
export const READER_CHROME_IDLE_MS = 2800;

/** Prefer reduced-motion media query when available. */
export function prefersReducedMotion(media = globalThis.matchMedia) {
  try {
    return Boolean(media?.("(prefers-reduced-motion: reduce)")?.matches);
  } catch {
    return false;
  }
}

/** Class list for the calm reading room shell. */
export function readerCalmClassNames({ chromeDim = false, reducedMotion = false } = {}) {
  const parts = ["reader", "reader-calm"];
  if (chromeDim && !reducedMotion) parts.push("is-chrome-dim");
  return parts.join(" ");
}
