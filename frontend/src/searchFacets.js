/** Client-side Search facets from the current result set — no recrawl. */

export const FORMAT_FACETS = [
  ["book", "Book"],
  ["audiobook", "Audiobook"],
  ["magazine", "Magazine"],
  ["comic", "Comic"],
  ["music", "Music"],
];

export const WHERE_FACETS = [
  ["shelf", "On the shelf"],
  ["beyond", "Beyond"],
  ["public_domain", "Public domain"],
];

export function emptyFacetSelection() {
  return { format: "", where: "", year: "" };
}

export function countSearchFacets({ local = [], beyond = [], public_domain = [] } = {}) {
  const formats = Object.fromEntries(FORMAT_FACETS.map(([key]) => [key, 0]));
  const where = {
    shelf: Array.isArray(local) ? local.length : 0,
    beyond: Array.isArray(beyond) ? beyond.length : 0,
    public_domain: Array.isArray(public_domain) ? public_domain.length : 0,
  };
  const years = {};
  const all = [...(local || []), ...(beyond || []), ...(public_domain || [])];
  for (const item of all) {
    const kind = String(item?.kind || "").toLowerCase();
    if (kind in formats) formats[kind] += 1;
    const year = String(item?.year || "").trim();
    if (year) years[year] = (years[year] || 0) + 1;
  }
  return { formats, where, years };
}

export function applySearchFacets(result = {}, { format = "", where = "", year = "" } = {}) {
  const match = (item, bucket) => {
    if (format && String(item?.kind || "") !== format) return false;
    if (where && bucket !== where) return false;
    if (year && String(item?.year || "") !== String(year)) return false;
    return true;
  };
  return {
    local: (result.local || []).filter((item) => match(item, "shelf")),
    beyond: (result.beyond || []).filter((item) => match(item, "beyond")),
    public_domain: (result.public_domain || []).filter((item) => match(item, "public_domain")),
  };
}

export function yearFacetEntries(years = {}) {
  return Object.entries(years)
    .filter(([, count]) => count > 0)
    .sort((a, b) => Number(b[0]) - Number(a[0]));
}
