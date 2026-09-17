/** Display-only junk strip — keeps author initials (unlike stripPartMarkers). */
const EXT_TAIL = /\.(mp3|m4b|m4a|flac|ogg|wav|aac|nzb|par2|rar|zip|7z|nfo|sfv)(?:\b|$)/gi;
const YENC = /\byenc\b/gi;
const BARE_SLASH_PART = /\b\d{1,3}\s*\/\s*\d{1,3}\b/g;
const BRACKET_PART = /\[\d+\s*\/\s*\d+\]/g;
const PAREN_PART = /\(\d+\s*\/\s*\d+\)/g;
const OF_PART = /\b\d{1,3}\s*of\s*\d{1,3}\b/gi;
const NAMED_PART = /\b(?:part|cd|disc|disk)\s*\d{1,3}(?:\s*(?:\/|of)\s*\d{1,3})?\b/gi;

export function stripDisplayJunk(title = "") {
  let text = String(title || "");
  text = text.replace(BRACKET_PART, " ");
  text = text.replace(PAREN_PART, " ");
  text = text.replace(OF_PART, " ");
  text = text.replace(NAMED_PART, " ");
  text = text.replace(BARE_SLASH_PART, " ");
  text = text.replace(EXT_TAIL, " ");
  text = text.replace(YENC, " ");
  text = text.replace(/\s*[-–—|:]\s*$/g, "");
  text = text.replace(/\s{2,}/g, " ").trim();
  return text;
}

/** Known comic/magazine imprints — matched case-insensitively after normalizing punctuation. */
const PUBLISHER_LABELS = {
  image: "Image",
  "image comics": "Image Comics",
  marvel: "Marvel",
  "marvel comics": "Marvel Comics",
  dc: "DC",
  "dc comics": "DC Comics",
  idw: "IDW",
  "idw publishing": "IDW",
  dynamite: "Dynamite",
  "dynamite entertainment": "Dynamite",
  "dark horse": "Dark Horse",
  "dark horse comics": "Dark Horse",
  tokyopop: "TokyoPop",
  "tokyo pop": "TokyoPop",
  boom: "BOOM!",
  "boom studios": "BOOM!",
  "boom! studios": "BOOM!",
  valiant: "Valiant",
  "valiant entertainment": "Valiant",
  oni: "Oni",
  "oni press": "Oni Press",
  ablaze: "Ablaze",
  titan: "Titan",
  "titan comics": "Titan Comics",
  viz: "VIZ",
  "viz media": "VIZ Media",
  kodansha: "Kodansha",
  "yen press": "Yen Press",
  "seven seas": "Seven Seas",
  vertical: "Vertical",
  fantagraphics: "Fantagraphics",
  archie: "Archie",
  "archie comics": "Archie Comics",
  "avatar press": "Avatar Press",
  aftershock: "Aftershock",
  skybound: "Skybound",
  vault: "Vault",
  scout: "Scout",
  "heavy metal": "Heavy Metal",
  "humanoids": "Humanoids",
  "top cow": "Top Cow",
  "wildstorm": "WildStorm",
  "vertigo": "Vertigo",
};

const PUBLISHER_KEYS = new Set(Object.keys(PUBLISHER_LABELS));
const IMPRINT_SUFFIX = /\b(comics?|studios?|press|publishing|entertainment|manga|media|house)\b/i;
const AUTHOR_INITIAL = /\b[A-Z]\.\s+[A-Z]/;
const DASH_SPLIT = /\s+[-–—]\s+/;

function normalizeKey(value) {
  return String(value || "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function isKnownPublisher(segment) {
  return PUBLISHER_KEYS.has(normalizeKey(segment));
}

/** ALL-CAPS imprint token(s): TOKYOPOP, IMAGE COMICS — not mixed-case authors. */
export function isAllCapsImprint(segment = "") {
  const text = String(segment || "").trim();
  if (text.length < 2 || text.length > 40) return false;
  if (!/[A-Za-z]/.test(text)) return false;
  if (/[a-z]/.test(text)) return false;
  const words = text.split(/\s+/).filter(Boolean);
  if (!words.length || words.length > 4) return false;
  return /^[A-Z0-9][A-Z0-9\s&'.!/-]*$/.test(text);
}

function prettifyPublisher(segment) {
  const key = normalizeKey(segment);
  if (PUBLISHER_LABELS[key]) return PUBLISHER_LABELS[key];
  const text = String(segment || "").trim();
  if (isAllCapsImprint(text)) {
    return text
      .split(/\s+/)
      .map((word) => {
        if (word.length <= 3 && /^[A-Z0-9]+$/.test(word)) return word;
        return word.charAt(0) + word.slice(1).toLowerCase();
      })
      .join(" ");
  }
  return text;
}

/**
 * Left-of-dash looks like a publisher imprint (not an author).
 * Comics/magazines: known list, ALL CAPS, or imprint suffix (Comics/Press/…).
 * Books/audiobooks: known list only — keep "Author - Title".
 * Other kinds: known list or ALL CAPS imprint.
 */
export function shouldDemotePublisherPrefix(left = "", { kind = "" } = {}) {
  const segment = String(left || "").trim();
  if (!segment) return false;
  const kindKey = String(kind || "").toLowerCase();
  const bookish = kindKey === "book" || kindKey === "audiobook" || kindKey === "gap";
  const aggressive = kindKey === "comic" || kindKey === "magazine";

  if (isKnownPublisher(segment)) return true;
  if (bookish) return false;
  if (isAllCapsImprint(segment)) return true;
  if (!aggressive) return false;
  if (AUTHOR_INITIAL.test(segment)) return false;
  return IMPRINT_SUFFIX.test(segment);
}

/**
 * Split a release/indexer title into a glanceable primary + demoted publisher.
 * Preserves full raw string for tips/peek; primary leads with the distinctive name.
 */
export function displayTitleParts(title = "", { kind = "" } = {}) {
  const raw = String(title || "").trim();
  if (!raw) return { primary: "", secondary: "", raw: "", full: "" };

  const cleaned = stripDisplayJunk(raw) || raw;
  const chunks = cleaned.split(DASH_SPLIT).map((part) => part.trim()).filter(Boolean);

  if (chunks.length < 2) {
    return { primary: cleaned, secondary: "", raw, full: cleaned };
  }

  const left = chunks[0];
  const right = chunks.slice(1).join(" - ");
  if (!shouldDemotePublisherPrefix(left, { kind })) {
    return { primary: cleaned, secondary: "", raw, full: cleaned };
  }

  const secondary = prettifyPublisher(left);
  const primary = right;
  return {
    primary,
    secondary,
    raw,
    full: secondary ? `${primary} · ${secondary}` : primary,
  };
}

export function displayPrimaryTitle(title = "", opts = {}) {
  return displayTitleParts(title, opts).primary;
}
