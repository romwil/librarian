/** Build `/browse` query URLs for Stacks (author A–Z, kind, series, favorites). */

const BROWSE_KINDS = ["book", "magazine", "comic", "audiobook", "music"];

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
  // Phase B: genre query key reserved once subjects land.
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

export const BROWSE_LETTERS = [
  "#",
  ..."ABCDEFGHIJKLMNOPQRSTUVWXYZ".split(""),
];
