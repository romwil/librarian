/** Search-lane copy and role defaults. Stay off copy.js (Phase 1 owns that file). */

export const ASK_THE_HOUSE = "Ask the house";
export const ASK_THE_HOUSE_PROMPT = "Not on these shelves?";
export const DISCLOSURE_TITLE = "Ask the house?";
export const DISCLOSURE_STAY = "Stay on the shelves";
export const DISCLOSURE_STORAGE_KEY = "librarian.searchBeyondDisclosure";

export function shouldAutoBeyond(role) {
  return role === "owner" || role === "op";
}

export function beyondDisclosureBody({ indexers = [], model = "", publicDomain = [] } = {}) {
  const indexerBit = indexers.length ? indexers.join(", ") : "this house's Usenet indexer";
  const modelBit = model || "its language model";
  const pdBit = publicDomain.length ? publicDomain.join(" and ") : "public-domain libraries";
  return `Ask the house files this title for the owner. Later, the house may send these search words to ${indexerBit}, ${modelBit}, and ${pdBit}. They don't learn who you are. Nothing downloads until the owner confirms.`;
}

export function readerSawDisclosure(storage = globalThis.localStorage) {
  try {
    return storage?.getItem(DISCLOSURE_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

export function rememberDisclosure(storage = globalThis.localStorage) {
  try {
    storage?.setItem(DISCLOSURE_STORAGE_KEY, "1");
  } catch {
    /* private mode */
  }
}

export function searchFieldParams(bag = {}, { mode = "" } = {}) {
  const extras = {
    kind: bag.kind || "",
    mode: mode || "",
    title: bag.title,
    author: bag.author,
    isbn: bag.isbn,
    series: bag.series,
    issue: bag.issue,
    artist: bag.artist,
    album: bag.album,
    year: bag.year,
  };
  return extras;
}
