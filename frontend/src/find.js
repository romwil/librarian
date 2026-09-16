export const KINDS = [
  ["", "All"],
  ["book", "Book"],
  ["magazine", "Magazine"],
  ["comic", "Comic"],
  ["audiobook", "Audiobook"],
  ["music", "Music"],
];

export const EXTRA_FIND_KINDS = [
  ["movie", "Movie"],
  ["tv", "TV"],
  ["xxx", "XXX"],
];

export const FIND_KEYS = ["q", "kind", "author", "title", "isbn", "series", "issue", "artist", "album", "year"];

export const FIND_FIELDS_BY_KIND = {
  "": [],
  book: ["title", "author", "isbn", "year"],
  magazine: ["title", "author", "isbn", "year"],
  comic: ["series", "issue", "year"],
  music: ["artist", "album", "year"],
  audiobook: ["title", "author"],
  movie: ["title", "year"],
  tv: ["title", "year"],
  xxx: ["title", "year"],
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

export function shouldShowDiscover(fields = {}) {
  return !hasFindQuery(fields);
}

export function findKindOptions(showExtra = false) {
  return showExtra ? [...KINDS, ...EXTRA_FIND_KINDS] : KINDS;
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
  return qs ? `/find?${qs}` : "/find";
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
  if (kind === "movie") return "Movie title";
  if (kind === "tv") return "Show title";
  if (kind === "xxx") return "Title";
  return "Beyond the shelves";
}

export function gapFindFields(work = {}) {
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

export function selectedFromHit(item = {}) {
  return {
    guid: item.guid || "",
    title: item.title || "",
    download_url: item.download_url || "",
    category: item.category,
    size: item.size,
    cover: item.cover || "",
    poster: item.poster || "",
    category_name: item.category_name || "",
    author: item.author || "",
    isbn: item.isbn || "",
    book_title: item.book_title || "",
    kind: item.kind || "",
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

export function requestBodyFromHit(item = {}, sought = {}) {
  const fields = pruneFieldsForKind(sought.kind || item.kind || "", sought);
  const selected = selectedFromHit(item);
  const title =
    item.book_title ||
    fields.title ||
    fields.album ||
    (fields.series && fields.issue ? `${fields.series} #${fields.issue}` : fields.series) ||
    item.title ||
    "";
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
    poster: selected.poster,
    category_name: selected.category_name,
    size: selected.size,
    sought: fields,
    selected,
    host_id: selected.host_id,
    host_name: selected.host_name,
  };
}
