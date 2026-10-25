/** Build `/browse` query URLs for Stacks (author A–Z, kind, series, favorites). */

const BROWSE_KINDS = ["book", "magazine", "comic", "audiobook", "music"];

/** Facets that become meaningless when kind changes. */
const KIND_SCOPED_KEYS = ["author", "letter", "series", "genre"];

/** Named shelf ids are `uuid4().hex` (32 hex chars). Anything else is dropped. */
const NAMED_SHELF_ID = /^[a-f0-9]{32}$/i;

/**
 * Stacks shelf filter: Favorites, or a household shelf id.
 * Hostile or unknown values become "" so a bad query cannot blank the page.
 */
export function normalizeBrowseShelf(value) {
  const shelf = String(value || "").trim();
  if (!shelf) return "";
  if (shelf.toLowerCase() === "favorites") return "favorites";
  if (NAMED_SHELF_ID.test(shelf)) return shelf.toLowerCase();
  return "";
}

/** Sort keys the stacks command bar and `GET /api/browse` both understand. */
export const BROWSE_SORTS = ["author", "title", "updated", "year"];

/** Library-word labels for the sort select, in display order. */
export const BROWSE_SORT_OPTIONS = [
  ["author", "Author"],
  ["title", "Title"],
  ["year", "Year"],
  ["updated", "Recently shelved"],
];

/** Columns the CSV export and the List view both recognize. */
export const BROWSE_EXPORT_COLUMNS = ["title", "author", "year", "kind", "series", "genre"];

const DEFAULT_LIST_COLUMNS = ["title", "author", "year", "kind"];

/**
 * Sensible per-sort direction when the household hasn't picked one —
 * author/title read A→Z, updated/year read newest-first.
 */
export function defaultSortDir(sort) {
  const key = BROWSE_SORTS.includes(sort) ? sort : "author";
  return key === "updated" || key === "year" ? "desc" : "asc";
}

/** Patch to apply when the Sort select changes — resets direction to that sort's default. */
export function sortChangePatch(nextSort) {
  const key = String(nextSort || "").trim().toLowerCase();
  const sort = BROWSE_SORTS.includes(key) ? key : "author";
  return { sort, sort_dir: defaultSortDir(sort) };
}

export function sortDirLabel(dir) {
  return String(dir || "").toLowerCase() === "desc" ? "Descending" : "Ascending";
}

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

/**
 * Shared query-string builder for `/browse` (router), `GET /api/browse` (fetch),
 * and `GET /api/browse/export.csv` — one place that decides which params are
 * worth writing, so the three stay in lockstep.
 */
export function browseQueryParams(filters = {}, { offset, limit } = {}) {
  const params = new URLSearchParams();
  const kind = String(filters.kind || "").trim();
  const author = String(filters.author || "").trim();
  const letter = String(filters.letter || "").trim().toUpperCase();
  const series = String(filters.series || "").trim();
  const shelf = normalizeBrowseShelf(filters.shelf);
  const sortRaw = String(filters.sort || "").trim().toLowerCase();
  const sort = BROWSE_SORTS.includes(sortRaw) ? sortRaw : "author";
  const sortDirRaw = String(filters.sort_dir || filters.sortDir || "").trim().toLowerCase();
  const genre = String(filters.genre || "").trim();
  if (kind) params.set("kind", kind);
  if (author) params.set("author", author);
  if (letter) params.set("letter", letter);
  if (series) params.set("series", series);
  if (shelf) params.set("shelf", shelf);
  if (sort && sort !== "author") params.set("sort", sort);
  if (genre) params.set("genre", genre);
  if ((sortDirRaw === "asc" || sortDirRaw === "desc") && sortDirRaw !== defaultSortDir(sort)) {
    params.set("sort_dir", sortDirRaw);
  }
  if (offset != null) params.set("offset", String(offset));
  if (limit != null) params.set("limit", String(limit));
  return params;
}

export function browseHref(filters = {}) {
  const qs = browseQueryParams(filters).toString();
  return qs ? `/browse?${qs}` : "/browse";
}

export function browseFiltersFromSearchParams(params) {
  const get = (key) => {
    if (typeof params?.get === "function") return String(params.get(key) || "").trim();
    return String(params?.[key] || "").trim();
  };
  const letter = get("letter").toUpperCase();
  const shelf = normalizeBrowseShelf(get("shelf"));
  const sortRaw = get("sort").toLowerCase();
  const sort = BROWSE_SORTS.includes(sortRaw) ? sortRaw : "author";
  const sortDirRaw = get("sort_dir").toLowerCase();
  const sortDir = sortDirRaw === "asc" || sortDirRaw === "desc" ? sortDirRaw : defaultSortDir(sort);
  return {
    kind: get("kind"),
    author: get("author"),
    letter: letter === "#" || (letter.length === 1 && letter >= "A" && letter <= "Z") ? letter : "",
    series: get("series"),
    shelf,
    sort,
    sort_dir: sortDir,
    genre: get("genre"),
  };
}

/**
 * Validate + canonicalize an export/list column selection. Accepts a comma
 * string, an array, or nullish (→ no columns = "all" per the export API).
 * Unknown/hostile entries are dropped; order is always the canonical column order.
 */
export function normalizeExportColumns(columns) {
  if (columns == null) return [];
  const raw = Array.isArray(columns) ? columns : String(columns).split(",");
  const wanted = new Set(
    raw.map((value) => String(value ?? "").trim().toLowerCase()).filter(Boolean),
  );
  return BROWSE_EXPORT_COLUMNS.filter((col) => wanted.has(col));
}

/** `columns=` value for the export URL — omitted entirely when it's "all columns". */
export function browseExportColumnsParam(columns) {
  const normalized = normalizeExportColumns(columns);
  if (!normalized.length || normalized.length === BROWSE_EXPORT_COLUMNS.length) return "";
  return normalized.join(",");
}

/** `GET /api/browse/export.csv` URL for the current filters + column choice. */
export function browseExportHref(filters = {}, { columns } = {}) {
  const params = browseQueryParams(filters);
  const columnsParam = browseExportColumnsParam(columns);
  if (columnsParam) params.set("columns", columnsParam);
  const qs = params.toString();
  return `/api/browse/export.csv${qs ? `?${qs}` : ""}`;
}

const LIST_COLUMNS_KEY = "librarian.browse.listColumns";

/** List-view column preference, persisted locally — same idea as the facet folds below. */
export function loadBrowseListColumns(storage = globalThis.localStorage) {
  try {
    const raw = storage?.getItem?.(LIST_COLUMNS_KEY);
    if (!raw) return [...DEFAULT_LIST_COLUMNS];
    const normalized = normalizeExportColumns(JSON.parse(raw));
    return normalized.length ? normalized : [...DEFAULT_LIST_COLUMNS];
  } catch {
    return [...DEFAULT_LIST_COLUMNS];
  }
}

export function saveBrowseListColumns(columns, storage = globalThis.localStorage) {
  const normalized = normalizeExportColumns(columns);
  const next = normalized.length ? normalized : [...DEFAULT_LIST_COLUMNS];
  try {
    storage?.setItem?.(LIST_COLUMNS_KEY, JSON.stringify(next));
  } catch {
    /* private mode / quota — ignore */
  }
  return next;
}

/** Toggle one column on/off; never drops to zero columns (list rows need something to show). */
export function toggleBrowseListColumn(current, column, storage = globalThis.localStorage) {
  const key = String(column || "").trim().toLowerCase();
  if (!BROWSE_EXPORT_COLUMNS.includes(key)) return normalizeExportColumns(current);
  const base = normalizeExportColumns(current);
  const next = base.includes(key) ? base.filter((col) => col !== key) : [...base, key];
  return saveBrowseListColumns(next.length ? next : base, storage);
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

/** Heading bits that match visible active filters (shelf · kind · author · series · genre · letter). */
export function browseHeading(filters = {}, shelfName = "") {
  const bits = [];
  const named = String(shelfName || "").trim();
  if (filters.shelf === "favorites") bits.push("Favorites");
  else if (filters.shelf && named) bits.push(named);
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

/** Stacks page-size choices for the command bar's "Per page" select. */
export const BROWSE_PAGE_SIZES = [24, 48, 96];

const VIEW_KEY = "librarian.browse.view";

/** Covers (grid) or List — a local view preference, not part of the query string. */
export function loadBrowseView(storage = globalThis.localStorage) {
  try {
    const raw = String(storage?.getItem?.(VIEW_KEY) || "").trim().toLowerCase();
    return raw === "list" ? "list" : "covers";
  } catch {
    return "covers";
  }
}

export function saveBrowseView(view, storage = globalThis.localStorage) {
  const next = String(view || "").trim().toLowerCase() === "list" ? "list" : "covers";
  try {
    storage?.setItem?.(VIEW_KEY, next);
  } catch {
    /* private mode / quota — ignore */
  }
  return next;
}

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