/** Build `/browse` query URLs for Stacks (author A–Z, kind, series, favorites). */

const BROWSE_KINDS = ["book", "magazine", "comic", "audiobook", "music"];

/** Facets that become meaningless when kind changes. */
const KIND_SCOPED_KEYS = ["author", "letter", "series", "genre"];

export function browseKinds() {
  return [...BROWSE_KINDS];
}

export function browseHref(filters = {}) {
  const params = new URLSearchParams();
  const kind = String(filters.kind || "").trim();
  const author = String(filters.author || "").trim();
  const letter = String(filters.letter || "").trim().toUpperCase();
  const series = String(filters.series || "").trim();
  const shelf = String(filters.shelf || "").trim().toLowerCase();
  const sort = String(filters.sort || "").trim().toLowerCase();
  const genre = String(filters.genre || "").trim();
  if (kind) params.set("kind", kind);
  if (author) params.set("author", author);
  if (letter) params.set("letter", letter);
  if (series) params.set("series", series);
  if (shelf === "favorites") params.set("shelf", "favorites");
  if (sort && sort !== "author") params.set("sort", sort);
  if (genre) params.set("genre", genre);
  const qs = params.toString();
  return qs ? `/browse?${qs}` : "/browse";
}

export function browseFiltersFromSearchParams(params) {
  const get = (key) => {
    if (typeof params?.get === "function") return String(params.get(key) || "").trim();
    return String(params?.[key] || "").trim();
  };
  const letter = get("letter").toUpperCase();
  const shelf = get("shelf").toLowerCase();
  const sort = get("sort").toLowerCase() || "author";
  return {
    kind: get("kind"),
    author: get("author"),
    letter: letter === "#" || (letter.length === 1 && letter >= "A" && letter <= "Z") ? letter : "",
    series: get("series"),
    shelf: shelf === "favorites" ? "favorites" : "",
    sort: ["author", "title", "updated"].includes(sort) ? sort : "author",
    genre: get("genre"),
  };
}

/**
 * Merge a selected facet into the top-N chip list so deep-linked values
 * that fall outside the popular set remain visible and clearable.
 */
export function mergeFacetSelection(rows, selected, { limit = 16 } = {}) {
  const capped = Math.max(1, Math.min(Number(limit) || 16, 100));
  const list = Array.isArray(rows)
    ? rows
        .filter((row) => row && String(row.name || "").trim())
        .map((row) => ({
          name: String(row.name).trim(),
          count: row.count == null ? null : Number(row.count),
        }))
    : [];
  const name = String(selected || "").trim();
  if (!name) return list.slice(0, capped);

  const idx = list.findIndex((row) => row.name.toLowerCase() === name.toLowerCase());
  if (idx >= 0) {
    const [row] = list.splice(idx, 1);
    return [row, ...list].slice(0, capped);
  }
  return [{ name, count: null }, ...list].slice(0, capped);
}

/** Apply a chip patch; changing kind clears kind-scoped facets. */
export function applyBrowseFilterPatch(current, patch = {}) {
  const base = current && typeof current === "object" ? current : {};
  const next = { ...base, ...patch };
  if (Object.prototype.hasOwnProperty.call(patch, "kind") && String(patch.kind || "") !== String(base.kind || "")) {
    for (const key of KIND_SCOPED_KEYS) {
      next[key] = "";
    }
  }
  return next;
}

export function browseHasActiveFilters(filters = {}) {
  return Boolean(
    filters.kind ||
      filters.author ||
      filters.letter ||
      filters.series ||
      filters.genre ||
      filters.shelf,
  );
}

/** Heading bits that match visible active filters (kind · author · series · genre · letter). */
export function browseHeading(filters = {}) {
  const bits = [];
  if (filters.shelf === "favorites") bits.push("Favorites");
  if (filters.kind) bits.push(filters.kind);
  if (filters.author) bits.push(filters.author);
  if (filters.series) bits.push(filters.series);
  if (filters.genre) bits.push(filters.genre);
  if (filters.letter) bits.push(`Letter ${filters.letter}`);
  return bits.length ? bits.join(" · ") : "The stacks";
}

/** Object suitable for react-router setSearchParams (full replace). */
export function browseParamsObject(filters = {}) {
  const href = browseHref(filters);
  const qs = href.includes("?") ? href.slice(href.indexOf("?") + 1) : "";
  return qs ? Object.fromEntries(new URLSearchParams(qs)) : {};
}

export const BROWSE_LETTERS = [
  "#",
  ..."ABCDEFGHIJKLMNOPQRSTUVWXYZ".split(""),
];
