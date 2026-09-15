const LOGIN_COPY = {
  401: "That name or password did not match. Try again, or ask the owner for a join link.",
  429: "Too many tries. Wait a minute, then knock again.",
};

const UNREACHABLE_COPY = "Can't reach Librarian — is it running?";

function isUnreachable(error, raw) {
  if (error?.status) return false;
  return (
    /failed to fetch/i.test(raw) ||
    /networkerror/i.test(raw) ||
    /network request failed/i.test(raw) ||
    /^load failed$/i.test(raw) ||
    /failed to connect/i.test(raw)
  );
}

const INDEXER_COPY = [
  [/api_token is not configured/i, "Beyond the shelves needs an NZBFinder token in Settings."],
  [/invalid or missing api_token/i, "The indexer token was refused. Check NZBFinder in Settings."],
  [/returned html/i, "The indexer URL looks wrong — it sent a web page, not search results."],
  [/xml newznab/i, "This indexer answered in the old XML dialect. Librarian needs NZBFinder v2 JSON."],
  [/returned non-json/i, "The indexer answered in a format we could not read. Try again in a moment."],
  [/nzbfinder http 5/i, "The indexer is having a moment. Try again shortly."],
  [/nzbfinder/i, "Could not reach Beyond the shelves. Check the indexer in Settings."],
];

const SAB_COPY = [
  [/api key is not configured/i, "SABnzbd needs its API key in Settings before Request can queue."],
  [/http 401|http 403/i, "SABnzbd refused the key. Check the downloader settings."],
  [/returned non-json|unexpected payload/i, "SABnzbd answered strangely. Check the downloader URL."],
  [/did not return nzo_id/i, "SABnzbd did not accept the NZB. Try another result."],
  [/sabnzbd/i, "The downloader did not answer. Check the SABnzbd URL in Settings."],
];

export const FIELD_HELP = {
  loginName: "The household name you were given — not an email.",
  loginPassword: "Your door key. Need a new one? Ask the owner for a join link.",
  joinName: "A short display name for this household. Not an email.",
  joinPassword: "At least 8 characters. This is the key for the glass door.",
  sabnzbd_url: "HTTP address of SABnzbd, such as http://downloader.sl:8080.",
  sabnzbd_api_key: "From SABnzbd Config → General. It stays on this host.",
  nzbfinder_url: "Indexer base URL. Leave the default unless you host a mirror.",
  nzbfinder_api_token: "NZBFinder API token. This is what powers Beyond the shelves.",
  books_root: "Where organized books land, usually under /data.",
  magazines_root: "Magazine issues land here after identify.",
  comics_root: "CBZ issues land here after identify.",
  audiobooks_root: "Audiobook folders land here — never in the music library.",
  incoming_music_root: "Unpromoted albums wait here until an op Promotes them.",
  music_root: "Plexamp library. Promote copies incoming albums here.",
  complete_root: "If SAB finishes at /downloads, map that path to files this process can read.",
  audiobook_target: "Where listeners open titles: Plex, Audiobookshelf, or Librarian only.",
  llm_base_url: "Optional. BYO OpenAI-compatible endpoint for identify help.",
  llm_api_key: "Optional. Never invents an ISBN; only assists Review.",
  llm_model: "Optional model name for identify.",
  household_name: "Shown quietly in the chrome. The Hall still says The Hall.",
  reviewKind: "Which shelf this item belongs on.",
  reviewTitle: "The name that will appear on the cover and in search.",
  reviewAuthor: "Author, artist, or magazine title as the byline.",
  reviewIsbn: "Optional. Librarian never invents one — only use digits you trust.",
  reviewSeries: "Series or magazine name, if this is an issue in a run.",
  reviewIndex: "Issue number, YYYY-MM for magazines, or disc/part index.",
  reviewFolder: "Folder this process can read. On Unraid, /downloads may need complete root remapped.",
  searchKind: "Narrows both the local stacks and Beyond the shelves.",
  searchAuthor: "Folded into the same search box — not a second app.",
  searchTitle: "Folded into the same search box.",
  searchIsbn: "Digits help the stacks find a specific edition.",
  searchSeries: "Series name, then issues can match locally or beyond.",
  searchYear: "Publication year, if you know it.",
};

export function emptyHallCopy({ owner = false, configured = false } = {}) {
  if (configured) {
    return {
      title: "The shelves are still bare",
      lede: "Request a volume from Search, or wait for the first organize to land.",
    };
  }
  return {
    title: "Open the stacks",
    lede: owner
      ? "Add an indexer and library roots in Settings. The Hall stays open while you do."
      : "Ask the owner to add an indexer. Covers will land here.",
  };
}

export function emptyReviewCopy() {
  return "The bagging area is empty. Happy-path books never stop here.";
}

export function emptyQueueCopy() {
  return "Nothing in flight. Living chips live on Search cards; this list is for asked slips and SAB exceptions.";
}

export function searchStatusLine({ q = "", kind = "", localCount = 0, beyondCount = 0, phase = "idle" } = {}) {
  const query = String(q || "").trim();
  if (!query) return "Type a title, author, ISBN, or series.";
  const kindBit = kind ? ` · ${kind}` : "";
  const head = `searched ${query}${kindBit}`;
  if (phase === "local") return `${head} · looking on the shelves…`;
  if (phase === "beyond") return `${head} · ${localCount} on shelves · looking beyond…`;
  if (phase === "beyond_error") return `${head} · ${localCount} on shelves · beyond could not be reached`;
  return `${head} · ${localCount} on shelves · ${beyondCount} beyond`;
}

export function detailText(detail) {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (typeof item === "string" ? item : item?.msg || item?.detail || ""))
      .filter(Boolean)
      .join(" ");
  }
  if (detail && typeof detail === "object") {
    return String(detail.msg || detail.detail || "");
  }
  return "";
}

function matchCopy(raw, table) {
  for (const [pattern, copy] of table) {
    if (pattern.test(raw)) return copy;
  }
  return "";
}

export function humanError(error, context = "") {
  const status = error?.status;
  const raw = String(error?.message || error || "").trim();
  if (isUnreachable(error, raw)) return UNREACHABLE_COPY;
  if (context === "login") {
    if (LOGIN_COPY[status]) return LOGIN_COPY[status];
    if (/invalid username or password/i.test(raw)) return LOGIN_COPY[401];
    if (/too many/i.test(raw)) return LOGIN_COPY[429];
  }
  if (context === "join" && /invite|token|not found/i.test(raw)) {
    return "That join link is missing or already used. Ask the owner for a new invite.";
  }
  for (const table of [INDEXER_COPY, SAB_COPY]) {
    for (const [, copy] of table) {
      if (raw === copy) return raw;
    }
  }
  const indexer = matchCopy(raw, INDEXER_COPY);
  if (indexer) return indexer;
  const sab = matchCopy(raw, SAB_COPY);
  if (sab) return sab;
  if (/authentication required/i.test(raw)) return "Sign in to continue.";
  if (/not allowed/i.test(raw)) return "That shelf is for the house keepers.";
  if (/owner has not been seeded/i.test(raw)) return "The reading room is not seeded yet.";
  if (/work not found/i.test(raw)) return "That volume is not on these shelves.";
  if (!raw || raw.length > 180 || /traceback|exception/i.test(raw)) {
    return "Something went wrong in the stacks. Try again, or check Settings.";
  }
  return raw;
}

export function setupComplete(settings) {
  if (!settings) return false;
  const sab = Boolean(String(settings.sabnzbd_url || "").trim()) && Boolean(settings.sabnzbd_api_key_set);
  const indexer = Boolean(settings.nzbfinder_api_token_set);
  const roots = Boolean(String(settings.books_root || "").trim());
  return sab && indexer && roots;
}

export function setupStepComplete(settings, step) {
  if (!settings) return false;
  if (step === 0) return Boolean(String(settings.sabnzbd_url || "").trim()) && Boolean(settings.sabnzbd_api_key_set);
  if (step === 1) return Boolean(settings.nzbfinder_api_token_set);
  if (step === 2) {
    return ["books_root", "magazines_root", "comics_root", "audiobooks_root"].every((key) =>
      String(settings[key] || "").trim(),
    );
  }
  if (step === 3) return Boolean(String(settings.complete_root || "").trim());
  return false;
}
