/**
 * Owner Sorting / Desk chrome badge calm (PRD-005).
 *
 * Exact open count always lives one click away (Library card → Sorting).
 * Outside chrome: clear at 0, quiet dot for 1–SHOW_COUNT_AT, loud count above.
 */

export const DESK_BADGE_SHOW_COUNT_AT = 5;

/**
 * @param {unknown} count
 * @returns {"clear" | "quiet" | "loud"}
 */
export function deskBadgeMode(count) {
  const n = Math.max(0, Math.floor(Number(count) || 0));
  if (n <= 0) return "clear";
  if (n <= DESK_BADGE_SHOW_COUNT_AT) return "quiet";
  return "loud";
}

/**
 * Visible nav label — no raw count until escalation threshold.
 * @param {string} base
 * @param {unknown} count
 */
export function deskNavVisibleLabel(base, count) {
  const label = String(base || "").trim() || "Desk";
  const mode = deskBadgeMode(count);
  if (mode === "loud") {
    return `${label} ${Math.floor(Number(count) || 0)}`;
  }
  return label;
}

/**
 * Accessible name — always includes the exact open count when > 0.
 * @param {string} base
 * @param {unknown} count
 */
export function deskNavAriaLabel(base, count) {
  const label = String(base || "").trim() || "Desk";
  const n = Math.max(0, Math.floor(Number(count) || 0));
  // Clear keeps accessible name === visible label so chrome locators stay stable.
  if (n <= 0) return label;
  if (n <= DESK_BADGE_SHOW_COUNT_AT) {
    return `${label}, ${n} open — open desk for the exact tally`;
  }
  return `${label}, ${n} open`;
}

/**
 * Library-card Sorting link — exact count always visible here.
 * @param {unknown} count
 */
export function deskMenuSortingLabel(count) {
  const n = Math.max(0, Math.floor(Number(count) || 0));
  if (n <= 0) return "Sorting";
  return `Sorting (${n})`;
}
