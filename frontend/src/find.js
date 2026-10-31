import { partSetFindFields } from "./findParts.js";

export const KINDS = [
  ["", "All"],
  ["book", "Book"],
  ["magazine", "Magazine"],
  ["comic", "Comic"],
  ["audiobook", "Audiobook"],
  ["music", "Music"],
];

export const FIND_KEYS = ["q", "kind", "author", "title", "isbn", "series", "issue", "artist", "album", "year"];

export const FIND_FIELDS_BY_KIND = {
  "": [],
  book: ["title", "author", "isbn", "year"],
  magazine: ["title", "author", "isbn", "year"],
  comic: ["series", "issue", "year"],
  music: ["artist", "album", "year"],
  audiobook: ["title", "author", "isbn"],
};

export function emptyFindFields() {
  return {
    q: "",
    kind: "",
    author: "",
    title: "",
    isbn: "",
    series: "",
    issue: "",
    artist: "",
    album: "",
    year: "",
  };
}

function trimmed(value) {
  return String(value || "").trim();
}

export function visibleFindFields(kind) {
  return FIND_FIELDS_BY_KIND[kind] || FIND_FIELDS_BY_KIND[""];
}

export function pruneFieldsForKind(kind, fields = {}) {
  const allowed = new Set(["q", "kind", ...visibleFindFields(kind)]);
  const next = emptyFindFields();
  next.kind = kind && kind !== "gap" ? kind : "";
  for (const key of FIND_KEYS) {
    if (key === "kind") continue;
    if (allowed.has(key)) next[key] = trimmed(fields[key]);
  }
  if (next.kind === "music") next.isbn = "";
  return next;
}

export function composeSearchQuery({
  q = "",
  author = "",
  title = "",
  isbn = "",
  series = "",
  issue = "",
  artist = "",
  album = "",
  year = "",
} = {}) {
  return [q, author, title, isbn, series, issue, artist, album, year].map(trimmed).filter(Boolean).join(" ");
}

export function hasFindQuery(fields = {}) {
  return Boolean(composeSearchQuery(fields));
}

export const MAX_LADDER_RUNGS = 3;

function isbn13(value) {
  const digits = trimmed(value).replace(/[-\s]/g, "");
  if (!/^\d{13}$/.test(digits)) return "";
  const total = digits
    .slice(0, 12)
    .split("")
    .reduce((sum, digit, index) => sum + Number(digit) * (index % 2 === 0 ? 1 : 3), 0);
  return String((10 - (total % 10)) % 10) === digits[12] ? digits : "";
}

function sameText(left, right) {
  const norm = (value) => trimmed(value).toLowerCase().replace(/[^a-z0-9]+/g, "");
  return norm(left) === norm(right);
}

/**
 * One precise query at a time, most exact first (mirrors the backend ladder).
 * Book / audiobook: ISBN-13 alone, title alone, then title and author.
 * Comic: series and issue, then series. Magazine: title, then title and issue date.
 * Music: album, then artist and album. Never every known field in one AND query.
 */
export function searchLadder(fields = {}) {
  const base = pruneFieldsForKind(trimmed(fields.kind), { ...emptyFindFields(), ...fields });
  const kind = base.kind;
  const rungs = [];
  const push = (rung, partial, q) => {
    rungs.push({ rung, q, ...pruneFieldsForKind(kind, { ...partial, q, kind }) });
  };
  if (kind === "book" || kind === "audiobook") {
    const isbn = isbn13(base.isbn);
    const title = base.title || base.q;
    const author = base.author;
    if (isbn) push("isbn", { isbn }, isbn);
    if (title) push("title", { title }, title);
    if (title && author && !sameText(title, author)) push("title_author", { title, author }, `${title} ${author}`);
    if (!rungs.length && author) push("author", { author }, author);
  } else if (kind === "magazine") {
    const title = base.title || base.q;
    if (title) {
      push("title", { title }, title);
      if (base.year && !title.includes(base.year)) {
        push("title_date", { title, year: base.year }, `${title} ${base.year}`);
      }
    }
  } else if (kind === "comic") {
    const series = base.series || base.q;
    if (series && base.issue) push("series_issue", { series, issue: base.issue }, `${series} ${base.issue}`);
    if (series) push("series", { series }, series);
  } else if (kind === "music") {
    const album = base.album || base.q;
    const artist = base.artist;
    if (album) push("album", { album }, album);
    if (album && artist && !sameText(album, artist)) push("artist_album", { artist, album }, `${artist} ${album}`);
    if (!rungs.length && artist) push("artist", { artist }, artist);
  } else {
    const q = base.q;
    if (q) push("query", {}, q);
  }
  return rungs.slice(0, MAX_LADDER_RUNGS);
}

/**
 * The single query string Find sends as ``q``: what the person typed, else the
 * first title-like ladder rung. The fielded bag still rides along for the ladder.
 */
export function searchRequestQuery(fields = {}) {
  const typed = trimmed(fields.q);
  if (typed) return typed;
  const ladder = searchLadder(fields);
  const named = ladder.find((rung) => rung.rung !== "isbn");
  const picked = (named || ladder[0])?.q;
  if (picked) return picked;
  const loose = ["title", "series", "album", "author", "artist", "isbn"].map((key) => trimmed(fields[key]));
  return loose.find(Boolean) || "";
}

export function shouldShowDiscover(fields = {}) {
  return !hasFindQuery(fields);
}

export function discoverCatFromSearchParams(params) {
  const read = (key) => {
    if (!params) return "";
    if (typeof params.get === "function") return trimmed(params.get(key));
    return trimmed(params[key]);
  };
  return read("discover") || read("cat") || "";
}

export function discoverHref({ discover = "", cat = "", kind = "" } = {}) {
  const id = trimmed(discover || cat);
  const params = new URLSearchParams();
  if (id) params.set("discover", id);
  const kindValue = trimmed(kind);
  if (kindValue) params.set("kind", kindValue);
  const qs = params.toString();
  return qs ? `/search?${qs}` : "/search";
}

/** Group Discover items into one rail per indexer category. */
export function groupDiscoverRails(items, categories) {
  const labels = new Map((categories || []).map((row) => [String(row.id), row.name || row.id]));
  const groups = [];
  const index = new Map();
  for (const item of items || []) {
    const cat = item.category != null && item.category !== "" ? String(item.category) : "feed";
    const title = item.category_name || labels.get(cat) || cat;
    if (!index.has(cat)) {
      index.set(cat, groups.length);
      groups.push({ id: cat, title, items: [] });
    }
    groups[index.get(cat)].items.push(item);
  }
  return groups;
}

/** Bestsellers / curated lists preset on Find (`?preset=nyt&list=&date=`). */
export function bestsellersHref({ list = "hardcover-fiction", date = "current" } = {}) {
  const params = new URLSearchParams();
  params.set("preset", "nyt");
  const slug = trimmed(list) || "hardcover-fiction";
  params.set("list", slug);
  const when = trimmed(date) || "current";
  if (when && when !== "current") params.set("date", when);
  return `/noted${params.toString() ? `?${params.toString()}` : ""}`;
}

export function bestsellersFromSearchParams(params) {
  const read = (key) => {
    if (!params) return "";
    if (typeof params.get === "function") return trimmed(params.get(key));
    return trimmed(params[key]);
  };
  if (read("preset") !== "nyt") return null;
  return {
    list: read("list") || "hardcover-fiction",
    date: read("date") || "current",
  };
}

/** Local shelves first; Find beyond when the title is not owned. */
export function nytHitHref(book = {}) {
  const shelvedId = trimmed(book?.shelved?.id);
  if (shelvedId) return `/works/${encodeURIComponent(shelvedId)}`;
  const title = trimmed(book?.title);
  const author = trimmed(book?.author);
  const isbn = trimmed(book?.isbn);
  const q = [author, title].filter(Boolean).join(" ") || title || isbn;
  return searchHref({ q, kind: "book", title, author, isbn });
}

export function nytHitFindHref(book = {}) {
  const title = trimmed(book?.title);
  const author = trimmed(book?.author);
  const isbn = trimmed(book?.isbn);
  const q = [author, title].filter(Boolean).join(" ") || title || isbn;
  return findHref({ q, kind: "book", title, author, isbn });
}

/** Newznab top-level parents (approx) for Discover chip grouping. */
export const NEWZNAB_PARENT_ORDER = ["1000", "3000", "4000", "7000"];

export const NEWZNAB_PARENT_LABELS = {
  "1000": "Console",
  "3000": "Audio",
  "4000": "PC",
  "7000": "Books",
};

function newznabFamilyId(catId) {
  const n = Number(String(catId || "").trim());
  if (!Number.isFinite(n) || n < 1000) return "";
  return String(Math.floor(n / 1000) * 1000);
}

/** Group leaf Discover categories under their Newznab parent. Dedupes by id. */
export function groupDiscoverCategories(categories = []) {
  const seen = new Set();
  const buckets = new Map();
  for (const row of categories || []) {
    if (!row || row.id == null || row.id === "") continue;
    const id = String(row.id);
    if (seen.has(id)) continue;
    seen.add(id);
    const parentId = trimmed(row.parent_id) || newznabFamilyId(id) || "other";
    const parentName =
      trimmed(row.parent_name) || NEWZNAB_PARENT_LABELS[parentId] || (parentId === "other" ? "Other" : parentId);
    if (!buckets.has(parentId)) {
      buckets.set(parentId, { id: parentId, name: parentName, categories: [] });
    }
    buckets.get(parentId).categories.push({ ...row, id });
  }
  const ordered = [];
  for (const key of NEWZNAB_PARENT_ORDER) {
    if (buckets.has(key)) ordered.push(buckets.get(key));
  }
  for (const [key, group] of buckets) {
    if (!NEWZNAB_PARENT_ORDER.includes(key)) ordered.push(group);
  }
  return ordered;
}


/** Per-feed rail slice vs category browse grid (mirrors backend defaults). */
export const DISCOVER_RAIL_LIMIT = 12;
export const DISCOVER_BROWSE_LIMIT = 50;

/** Search Discover is ebook trending only. It does not follow the kind chips. */
export const DISCOVER_EBOOK_CAT = "7020";
export const DISCOVER_PAGE_SIZE = 12;

export function discoverPageIndex(page = 0) {
  const n = Number(page);
  if (!Number.isFinite(n) || n <= 0) return 0;
  return Math.floor(n);
}

/** Query for one page of ebook trending. Page 0 omits offset. */
export function discoverFeedRequest(page = 0) {
  const index = discoverPageIndex(page);
  const request = {
    cat: DISCOVER_EBOOK_CAT,
    limit: DISCOVER_PAGE_SIZE,
  };
  const offset = index * DISCOVER_PAGE_SIZE;
  if (offset > 0) request.offset = offset;
  return request;
}

export function findKindOptions(showExtra = false) {
  void showExtra;
  return KINDS;
}

export function buildFindSearchParams(fields = {}, { prune = false } = {}) {
  const source = prune
    ? pruneFieldsForKind(trimmed(fields.kind), { ...emptyFindFields(), ...fields })
    : { ...emptyFindFields(), ...fields };
  const params = new URLSearchParams();
  for (const key of FIND_KEYS) {
    const value = trimmed(source[key]);
    if (value) params.set(key, value);
  }
  return params;
}

export function findFieldsFromSearchParams(params) {
  const read = (key) => {
    if (!params) return "";
    if (typeof params.get === "function") return trimmed(params.get(key));
    return trimmed(params[key]);
  };
  const raw = emptyFindFields();
  for (const key of FIND_KEYS) raw[key] = read(key);
  return raw;
}

export function findHref(fields = {}) {
  const qs = buildFindSearchParams(fields, { prune: true }).toString();
  return qs ? `/search?${qs}` : "/search";
}

export function searchHref(fields = {}) {
  const qs = buildFindSearchParams(fields).toString();
  return qs ? `/search?${qs}` : "/search";
}

export function findPlaceholder(kind) {
  if (kind === "comic") return "Series, or fill series and issue below";
  if (kind === "music") return "Artist or album";
  if (kind === "audiobook") return "Title or author";
  if (kind === "magazine") return "Magazine title";
  if (kind === "book") return "Title, or fill author / ISBN below";
  return "Beyond the shelves";
}

export function gapFindFields(work = {}) {
  if (trimmed(work.gap_type) === "multipart") {
    return pruneFieldsForKind(
      work.kind && work.kind !== "gap" ? work.kind : "",
      partSetFindFields(work),
    );
  }
  const kind = work.kind && work.kind !== "gap" ? work.kind : "";
  const series = trimmed(work.series_name);
  const issue = trimmed(work.missing_index || work.series_index);
  const title = trimmed(work.title);
  const author = trimmed(work.author);
  const year = work.year == null ? "" : trimmed(work.year);
  const isbn = trimmed(work.isbn);
  const composed = [series, issue].filter(Boolean).join(" ") || title;
  if (kind === "comic" || kind === "magazine") {
    return pruneFieldsForKind(kind, {
      q: composed,
      kind,
      series: kind === "comic" ? series : "",
      issue: kind === "comic" ? issue : "",
      title: kind === "magazine" ? composed : "",
      author,
      isbn,
      year: year || (kind === "magazine" && /^\d{4}-/.test(issue) ? issue.slice(0, 4) : ""),
    });
  }
  if (kind === "music") {
    const albumGap = trimmed(work.gap_type) === "music_album";
    return pruneFieldsForKind(kind, {
      q: albumGap ? title || series : composed,
      kind,
      artist: author,
      album: albumGap ? title || series : series || title,
      year,
    });
  }
  if (kind === "audiobook") {
    return pruneFieldsForKind(kind, {
      q: composed,
      kind,
      title: title || series,
      author,
      isbn,
      year,
    });
  }
  return pruneFieldsForKind(kind, {
    q: composed,
    kind,
    title: title || series,
    author,
    isbn,
    year,
  });
}

/** True when Find was opened from a Hall gap (series/issue or title+kind hole). */
export function isCatalogGapQuery(fields = {}) {
  const kind = trimmed(fields.kind);
  if (!kind || kind === "gap") return false;
  if (kind === "comic" && trimmed(fields.series) && trimmed(fields.issue)) return true;
  if (kind === "magazine" && (trimmed(fields.title) || trimmed(fields.q)) && trimmed(fields.year)) return true;
  if (kind === "music" && (trimmed(fields.album) || trimmed(fields.artist))) return true;
  if ((kind === "book" || kind === "audiobook") && trimmed(fields.title) && trimmed(fields.author)) return true;
  return Boolean(trimmed(fields.series) && trimmed(fields.issue));
}

/**
 * Kind-aware queries for Hall → Find catalog gaps: the search ladder, not the
 * full prefill ANDed together. Confirm / Request still required — never auto-queue.
 */
export function catalogGapFanoutQueries(fields = {}, { cap = MAX_LADDER_RUNGS } = {}) {
  return searchLadder(fields).slice(0, cap);
}

/** Rank beyond hits: complete multipart sets first, then fuller sets, then singles. */
export function rankBeyondByCompleteness(items = []) {
  const list = Array.isArray(items) ? items : [];
  return [...list].sort((a, b) => {
    const score = (row) => {
      if (row?.complete) return 100 + (Number(row.found) || 0);
      if (row?.found != null && row?.total) return (Number(row.found) / Number(row.total)) * 50 + Number(row.found);
      if (row?.parts) return Number(row.found) || row.parts.length;
      return 1;
    };
    return score(b) - score(a);
  });
}

export function selectedFromHit(item = {}) {
  return {
    guid: item.guid || "",
    title: item.title || "",
    download_url: item.download_url || "",
    category: item.category,
    size: item.size,
    cover: item.cover || item.poster || "",
    category_name: item.category_name || "",
    author: item.author || "",
    isbn: item.isbn || "",
    book_title: item.book_title || "",
    kind: item.kind || "",
    pub_date: item.pub_date || "",
    host_id: item.host_id || "",
    host_name: item.host_name || "",
    tmdb_id: item.tmdb_id,
    tvdb_id: item.tvdb_id,
    imdb_id: item.imdb_id || "",
  };
}

export function beyondHostName(item = {}) {
  return String(item.host_name || "").trim();
}

export function requestBodyFromHit(item = {}, sought = {}, extras = {}) {
  const fields = pruneFieldsForKind(sought.kind || item.kind || "", sought);
  const selected = selectedFromHit(item);
  const title =
    item.book_title ||
    fields.title ||
    fields.album ||
    (fields.series && fields.issue ? `${fields.series} #${fields.issue}` : fields.series) ||
    item.title ||
    "";
  const candidates = Array.isArray(extras.candidates)
    ? extras.candidates
    : Array.isArray(item.candidates)
      ? item.candidates
      : [];
  return {
    title,
    guid: selected.guid,
    kind: fields.kind || item.kind || undefined,
    category: selected.category != null && selected.category !== "" ? String(selected.category) : undefined,
    download_url: selected.download_url,
    author: fields.author || fields.artist || item.author || "",
    isbn: fields.kind === "music" ? "" : fields.isbn || item.isbn || "",
    q: fields.q,
    series: fields.series,
    issue: fields.issue,
    artist: fields.artist,
    album: fields.album,
    year: fields.year,
    cover: selected.cover,
    book_title: selected.book_title,
    category_name: selected.category_name,
    size: selected.size,
    sought: fields,
    selected,
    host_id: selected.host_id,
    host_name: selected.host_name,
    candidates,
    rank_method: extras.rank_method || item.rank_method || "",
    rank_reason: extras.rank_reason || item.rank_reason || "",
  };
}
