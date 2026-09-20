/** Build `/browse` query URLs for Stacks (author A–Z, kind, series, favorites). */

const BROWSE_KINDS = ["book", "magazine", "comic", "audiobook", "music"];

/** Facets that become meaningless when kind changes. */
const KIND_SCOPED_KEYS = ["author", "letter", "series", "genre"];

/** Singular / plural nouns for household shelf totals. */
const KIND_NOUNS = {
  book: ["book", "books"],
  magazine: ["magazine", "magazines"],
  comic: ["comic", "comics"],
  audiobook: ["audiobook", "audiobooks"],
  music: ["album", "albums"],
};

export function browseKinds() {
  return [...BROWSE_KINDS];
}

/** Locale-friendly integer for shelf counts (e.g. 1234 → "1,234"). */
export function formatShelfCount(count) {
  const n = Math.max(0, Math.floor(Number(count) || 0));
  return n.toLocaleString("en-US");
}

/**
 * Household line for a kind total — e.g. "1,234 books on the shelves",
 * "56 audiobooks", "1 comic on the shelves".
 */
export function kindShelfTotalLine(kind, count) {
  const key = String(kind || "").trim().toLowerCase();
  if (count == null || count === "") return "";
  const n = Math.max(0, Math.floor(Number(count) || 0));
  const formatted = formatShelfCount(n);
  const nouns = KIND_NOUNS[key];
  if (!nouns) return "";
  const noun = n === 1 ? nouns[0] : nouns[1];
  // Audiobooks read cleaner without the trailing "on the shelves".
  if (key === "audiobook") return `${formatted} ${noun}`;
  return `${formatted} ${noun} on the shelves`;
}

/** Lookup a kind's count from `/api/browse/facets` `kinds` rows or a hall map. */
export function kindCountFromFacets(facetsOrCounts, kind) {
  const key = String(kind || "").trim().toLowerCase();
  if (!key) return null;
  if (facetsOrCounts && typeof facetsOrCounts === "object" && !Array.isArray(facetsOrCounts)) {
    if (Array.isArray(facetsOrCounts.kinds)) {
      const row = facetsOrCounts.kinds.find((item) => String(item?.kind || "").toLowerCase() === key);
      return row ? Math.max(0, Math.floor(Number(row.count) || 0)) : 0;
    }
    if (Object.prototype.hasOwnProperty.call(facetsOrCounts, key)) {
      return Math.max(0, Math.floor(Number(facetsOrCounts[key]) || 0));
    }
  }
  return null;
}

/** Stacks grid count line — kind-aware when a media type filter is on. */
export function browseCountLine({ kind = "", shelf = "", total = 0, loading = false } = {}) {
  if (loading) return "Opening the stacks…";
  const n = Math.max(0, Math.floor(Number(total) || 0));
  const kindLine = kindShelfTotalLine(kind, n);
  if (kindLine) return kindLine;
  if (String(shelf || "").toLowerCase() === "favorites") {
    return n === 1 ? "1 favorite on the shelves" : `${formatShelfCount(n)} favorites on the shelves`;
  }
  return n === 0 ? "Nothing on the shelves yet" : `${formatShelfCount(n)} on the shelves`;
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

const FOLD_STORAGE_KEY = "librarian.browse.folds";
const FOLD_DEFAULTS = { author: false, series: false, genre: false };

/** Session-persisted expand state for Authors / Series / Genres (default collapsed). */
export function readBrowseFoldState(storage = globalThis.sessionStorage) {
  try {
    const raw = storage?.getItem?.(FOLD_STORAGE_KEY);
    if (!raw) return { ...FOLD_DEFAULTS };
    const parsed = JSON.parse(raw);
    return {
      author: Boolean(parsed?.author),
      series: Boolean(parsed?.series),
      genre: Boolean(parsed?.genre),
    };
  } catch {
    return { ...FOLD_DEFAULTS };
  }
}

export function toggleBrowseFold(current, id, storage = globalThis.sessionStorage) {
  const next = {
    author: Boolean(current?.author),
    series: Boolean(current?.series),
    genre: Boolean(current?.genre),
    [id]: !Boolean(current?.[id]),
  };
  try {
    storage?.setItem?.(FOLD_STORAGE_KEY, JSON.stringify(next));
  } catch {
    /* private mode / quota — ignore */
  }
  return next;
}