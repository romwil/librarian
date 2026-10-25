/**
 * Title-action menu logic — which action stays visible outside the ⋮ grip
 * (the Projectionist "one primary stays on the poster" rule, library-worded)
 * and which actions move into the portaled menu.
 *
 * Kept free of React/DOM so it is unit-testable with plain objects.
 */

/** Primary candidates, in priority order. "ask" only wins when nothing above it applies. */
const PRIMARY_ORDER = ["listen", "read", "open", "ask"];

/**
 * Decide the one action that stays outside the menu for the work hero and
 * the peek. Priority: Listen (or Continue listening) > Read in-app > Read
 * inline (non-readable-in-app but openable) > Ask the house — and Ask the
 * house is only offered here when the caller has already ruled out
 * Listen/Read/inline-open (mirrors the pre-menu peek/hero condition).
 *
 * Returns `null` when nothing qualifies — e.g. a rail card, where the cover
 * click itself is the primary (peek) and every action lives in the menu.
 */
export function primaryWorkAction({
  canListen = false,
  listenResume = false,
  listenLabel = "",
  canRead = false,
  canInlineOpen = false,
  readLabel = "Read",
  canAsk = false,
  askLabel = "Ask the house",
} = {}) {
  if (canListen) {
    return { key: "listen", label: listenLabel || (listenResume ? "Continue listening" : "Listen") };
  }
  if (canRead) {
    return { key: "read", label: readLabel || "Read" };
  }
  if (canInlineOpen) {
    return { key: "open", label: readLabel || "Read" };
  }
  if (canAsk) {
    return { key: "ask", label: askLabel || "Ask the house" };
  }
  return null;
}

/**
 * Split a flat action-descriptor list into the one primary (matched by key)
 * and the rest, which move into the menu. Hostile/empty input degrades
 * safely: no primary key, a non-array list, or a key with no match all just
 * leave everything in the menu instead of throwing or silently dropping items.
 */
export function splitWorkActions(actions, primaryKey = "") {
  const list = Array.isArray(actions) ? actions.filter(Boolean) : [];
  const key = String(primaryKey || "").trim();
  if (!key) return { primary: null, items: list };
  const idx = list.findIndex((action) => action && action.key === key);
  if (idx === -1) return { primary: null, items: list };
  const primary = list[idx];
  const items = list.filter((_, i) => i !== idx);
  return { primary, items };
}

/** Every key `primaryWorkAction` can return, in priority order — for callers building descriptor lists. */
export function primaryActionOrder() {
  return [...PRIMARY_ORDER];
}
