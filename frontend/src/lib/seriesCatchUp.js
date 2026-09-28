/** Series catch-up voice — mirrors `librarian.delight.catch_up_invitation` so
 *  Hall (server copy) and Work (client copy) read as the same house. */

const KIND_NOUNS = {
  comic: ["issue", "issues"],
  magazine: ["issue", "issues"],
  music: ["track", "tracks"],
  audiobook: ["part", "parts"],
  book: ["volume", "volumes"],
};

const GAP_TYPE_NOUNS = {
  multipart: ["part", "parts"],
  audiobook_parts: ["part", "parts"],
  music_tracks: ["track", "tracks"],
  music_album: ["album", "albums"],
  comic_issue: ["issue", "issues"],
  series_volume: ["volume", "volumes"],
};

const COUNT_WORDS = { 1: "One", 2: "Two", 3: "Three" };

function trimmed(value) {
  return String(value == null ? "" : value).trim();
}

export function catchUpNoun(kind, gapType = "", plural = false) {
  const pair = GAP_TYPE_NOUNS[trimmed(gapType)] || KIND_NOUNS[trimmed(kind)] || ["volume", "volumes"];
  return plural ? pair[1] : pair[0];
}

export function catchUpInvitation({ seriesName = "", kind = "", gapType = "", missingCount = 0 } = {}) {
  const count = Math.max(0, Number(missingCount) || 0);
  if (count < 1) return "";
  const noun = catchUpNoun(kind, gapType, count !== 1);
  const lead = COUNT_WORDS[count] || "A few";
  const name = trimmed(seriesName);
  return name ? `${lead} ${noun} from a whole ${name}.` : `${lead} ${noun} from a whole run.`;
}

/** Readers are invited to ask; owner/op go straight to Find. */
export function catchUpCtaLabel(role = "reader") {
  return role === "reader" ? "Ask the house" : "Find this hole";
}

/** Holes in a `series_ribbon` — owned/current beads are already on the shelf. */
export function missingRibbonBeads(ribbon = []) {
  const beads = Array.isArray(ribbon) ? ribbon : [];
  return beads.filter((bead) => bead?.state === "missing");
}
