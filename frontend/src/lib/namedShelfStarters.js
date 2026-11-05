/** Starter names for the named-shelf empty state (PRD-007 / UX-006). */

export const NAMED_SHELF_STARTERS = ["Next up", "For the beach", "Read together"];

export function shelfStarterNames(existing = []) {
  const taken = new Set(
    (Array.isArray(existing) ? existing : [])
      .map((shelf) => String(shelf?.name || "").trim().toLowerCase())
      .filter(Boolean),
  );
  return NAMED_SHELF_STARTERS.filter((name) => !taken.has(name.toLowerCase()));
}
