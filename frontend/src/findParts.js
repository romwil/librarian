/**
 * Client-side multipart detection for Find beyond results.
 * Indexers often return flat NZBs like "Title 01of32" or "CD1" — group them here.
 */

const EXT_TAIL = /\.(mp3|m4b|m4a|flac|ogg|wav|aac|nzb|par2|rar|zip|7z|nfo|sfv)(?:\b|$)/gi;
const YENC = /\byenc\b/gi;
const BRACKET_PART = /\[(\d+)\s*\/\s*(\d+)\]/;
const PAREN_PART = /\((\d+)\s*\/\s*(\d+)\)/;
const OF_PART = /\b(\d{1,3})\s*of\s*(\d{1,3})\b/i;
const NAMED_PART = /\b(?:part|cd|disc|disk)\s*(\d{1,3})(?:\s*(?:\/|of)\s*(\d{1,3}))?\b/i;
/** yEnc/article file index — strip for base titles only; never treat as a part marker. */
const BARE_SLASH_PART = /\b\d{1,3}\s*\/\s*\d{1,3}\b/g;
const NOISE_PREFIX = /^(?:attn\s+\S+\s+|nmr(?:t)?\s+|\[?[a-z0-9]{6,}\]\s*-?\s*)/i;

function namedMarkerStyle(raw) {
  const lower = String(raw || "").toLowerCase();
  if (lower.startsWith("cd")) return "cd";
  if (lower.startsWith("disc") || lower.startsWith("disk")) return "disc";
  return "part";
}

export function parsePartMarker(title = "") {
  const text = String(title || "");
  if (!text.trim()) return null;

  const bracket = text.match(BRACKET_PART);
  const paren = text.match(PAREN_PART);
  const ofMatch = text.match(OF_PART);
  const named = text.match(NAMED_PART);
  const namedWithTotal = Boolean(named && named[2]);

  // Prefer Part N/M / N of M over yEnc [N/M] or (N/M) when both present.
  if ((bracket || paren) && (ofMatch || namedWithTotal)) {
    if (ofMatch) {
      return {
        part: Number(ofMatch[1]),
        total: Number(ofMatch[2]),
        style: "of",
        raw: ofMatch[0],
      };
    }
    return {
      part: Number(named[1]),
      total: Number(named[2]),
      style: namedMarkerStyle(named[0]),
      raw: named[0],
    };
  }

  if (bracket) {
    return {
      part: Number(bracket[1]),
      total: Number(bracket[2]),
      style: "bracket",
      raw: bracket[0],
    };
  }

  if (paren) {
    return {
      part: Number(paren[1]),
      total: Number(paren[2]),
      style: "paren",
      raw: paren[0],
    };
  }

  if (ofMatch) {
    return {
      part: Number(ofMatch[1]),
      total: Number(ofMatch[2]),
      style: "of",
      raw: ofMatch[0],
    };
  }

  if (named) {
    const total = named[2] ? Number(named[2]) : null;
    return {
      part: Number(named[1]),
      total,
      style: namedMarkerStyle(named[0]),
      raw: named[0],
    };
  }

  return null;
}

export function stripPartMarkers(title = "") {
  let text = String(title || "");
  text = text.replace(BRACKET_PART, " ");
  text = text.replace(PAREN_PART, " ");
  text = text.replace(OF_PART, " ");
  text = text.replace(NAMED_PART, " ");
  // After named/bracket strips — bare N/M is a yEnc file index, not a release part.
  text = text.replace(BARE_SLASH_PART, " ");
  text = text.replace(EXT_TAIL, " ");
  text = text.replace(YENC, " ");
  text = text.replace(/[._]+/g, " ");
  text = text.replace(/\s*[-–—|:]\s*$/g, "");
  text = text.replace(/\s{2,}/g, " ").trim();
  return text;
}

export function normalizePartBase(title = "") {
  let text = stripPartMarkers(title).toLowerCase();
  text = text.replace(NOISE_PREFIX, "");
  text = text.replace(/[^a-z0-9]+/g, " ").replace(/\s+/g, " ").trim();
  return text;
}

export function partSetFingerprint(item = {}) {
  const title = item.title || "";
  const marker = parsePartMarker(title);
  if (!marker) return "";
  const base = normalizePartBase(title);
  if (!base) return "";
  const totalKey = marker.total != null ? String(marker.total) : "x";
  const host = String(item.host_id || item.host_name || "").trim().toLowerCase();
  return `${base}::${totalKey}::${host}`;
}

export function formatBytes(size) {
  const n = Number(size);
  if (!Number.isFinite(n) || n <= 0) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(n < 10 * 1024 ? 1 : 0)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(n < 10 * 1024 * 1024 ? 1 : 0)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export function displayPartSetTitle(items = [], markerTotal = null) {
  const first = items[0] || {};
  const raw = String(first.title || "");
  const quoted = raw.match(/"([^"]{6,})"/);
  let base = stripPartMarkers(quoted ? quoted[1] : raw);
  base = base.replace(NOISE_PREFIX, "").trim();
  base = base.replace(/^\[?[^\]]{0,40}\]\s*-?\s*/i, "").trim();
  if (!base) base = first.book_title || stripPartMarkers(raw) || "Multipart set";
  void markerTotal;
  return base;
}

function preferItem(a, b) {
  const sizeA = Number(a?.size) || 0;
  const sizeB = Number(b?.size) || 0;
  if (sizeA !== sizeB) return sizeA > sizeB ? a : b;
  return String(a?.title || "").length <= String(b?.title || "").length ? a : b;
}

/**
 * Split flat beyond hits into multipart sets and leftover singles.
 * A set needs a shared fingerprint and either ≥2 parts or a known total ≥ 2.
 */
export function groupBeyondItems(items = []) {
  const buckets = new Map();
  const singles = [];

  for (const item of items || []) {
    const marker = parsePartMarker(item?.title || "");
    const key = partSetFingerprint(item);
    if (!marker || !key) {
      singles.push(item);
      continue;
    }
    if (!buckets.has(key)) {
      buckets.set(key, {
        id: key,
        base: normalizePartBase(item.title),
        total: marker.total,
        style: marker.style,
        items: [],
      });
    }
    const bucket = buckets.get(key);
    if (marker.total != null && (bucket.total == null || marker.total > bucket.total)) {
      bucket.total = marker.total;
    }
    bucket.items.push({ ...item, _part: marker.part, _total: marker.total, _style: marker.style });
  }

  const sets = [];
  for (const bucket of buckets.values()) {
    const byPart = new Map();
    for (const item of bucket.items) {
      const part = item._part;
      if (!byPart.has(part)) byPart.set(part, []);
      byPart.get(part).push(item);
    }

    const parts = [...byPart.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([part, alts]) => {
        const primary = alts.reduce(preferItem);
        return {
          part,
          item: primary,
          alternatives: alts.filter((row) => row !== primary),
        };
      });

    const found = parts.length;
    const total = bucket.total != null ? bucket.total : found;
    const isSet = found >= 2 || (bucket.total != null && bucket.total >= 2);
    if (!isSet) {
      singles.push(...bucket.items.map(({ _part, _total, _style, ...rest }) => rest));
      continue;
    }

    const cleanItems = bucket.items.map(({ _part, _total, _style, ...rest }) => rest);
    const missing = missingParts(parts, bucket.total != null ? bucket.total : null);
    sets.push({
      id: bucket.id,
      title: displayPartSetTitle(cleanItems, total),
      total,
      found,
      complete: bucket.total != null && missing.length === 0,
      missing,
      /** NZBs for gap parts when the indexer listed them (rare); empty when gaps are unlisted. */
      missingItems: [],
      style: bucket.style,
      host_name: cleanItems[0]?.host_name || "",
      kind: cleanItems[0]?.kind || "",
      parts,
      items: cleanItems,
    });
  }

  sets.sort((a, b) => b.found - a.found || a.title.localeCompare(b.title));
  return { sets, singles };
}

/**
 * Usenet part markers are usually 1..N (01of32) but sometimes 0..N-1 (00of04).
 * If any observed part is 0, treat the set as 0-based.
 */
export function partIndexOrigin(parts = []) {
  for (const row of parts || []) {
    if (Number(row?.part) === 0) return 0;
  }
  return 1;
}

export function missingParts(parts, total) {
  if (total == null || total < 1) return [];
  const have = new Set((parts || []).map((row) => Number(row.part)));
  const origin = partIndexOrigin(parts);
  const last = origin === 0 ? total - 1 : total;
  const missing = [];
  for (let i = origin; i <= last; i += 1) {
    if (!have.has(i)) missing.push(i);
  }
  return missing;
}

export function partSetStatusLine(set) {
  if (!set) return "";
  const { found, total, complete, missing } = set;
  if (complete) return `${found}/${total} · complete`;
  if (total != null && total > found) {
    const gap = missing?.length ? ` · missing ${missing.length}` : "";
    return `${found}/${total} · incomplete${gap}`;
  }
  return `${found} parts`;
}

function itemSelectionKey(item) {
  return item?.guid || item?.title || "";
}

/**
 * Default checkbox selection for a multipart card.
 * Complete sets: select all listed NZBs. Incomplete with unlisted gaps: select none
 * (do not nudge a re-request of the few found parts). If gap NZBs were listed, select those.
 */
export function defaultPartSelectionKeys(set) {
  if (!set?.parts?.length) return [];
  const gapItems = set.missingItems || [];
  if (gapItems.length) {
    return gapItems.map(itemSelectionKey).filter(Boolean);
  }
  if (set.complete) {
    return set.parts.map((row) => itemSelectionKey(row.item)).filter(Boolean);
  }
  return [];
}

/**
 * Primary multipart CTA: never imply we can NZB-request ghost parts with no guid.
 * - complete → primary "Request complete set"
 * - gap NZBs listed → primary "Request missing (N)"
 * - gaps unlisted → secondary "Request listed (N)" for selected found parts only
 */
export function partSetRequestAction(set, selectedCount = 0) {
  const listed = set?.found ?? set?.parts?.length ?? 0;
  const gapItems = set?.missingItems || [];
  const gapCount = set?.missing?.length || 0;
  const n = Math.max(0, Number(selectedCount) || 0);
  const chased = Math.max(0, Number(set?.chaseQueriesTried) || 0);

  if (set?.complete) {
    return {
      kind: "complete",
      style: "primary",
      label: n > 0 && n === listed ? "Request complete set" : `Request listed (${n})`,
      enabled: n > 0,
      honesty: "",
    };
  }

  if (gapItems.length > 0) {
    return {
      kind: "missing-listed",
      style: "primary",
      label: n > 0 ? `Request missing (${n})` : `Request missing (${gapItems.length})`,
      enabled: n > 0,
      honesty: "",
    };
  }

  let honesty =
    gapCount > 0
      ? `Missing ${gapCount} part${gapCount === 1 ? "" : "s"} aren’t listed in these indexer results — refine the search or try another host.`
      : "Indexer only returned some parts — missing NZBs can’t be requested from this result.";
  if (chased > 0 && gapCount > 0) {
    honesty = `Tried ${chased} quer${chased === 1 ? "y" : "ies"} for missing parts — still unlisted. Request listed parts only, or refine the search.`;
  }

  return {
    kind: "listed-only",
    style: "secondary",
    label: n > 0 ? `Request listed (${n})` : "Request listed",
    enabled: n > 0,
    honesty,
  };
}

/** Cap secondary beyond searches when chasing missing multipart NZBs. */
export const GAP_CHASE_QUERY_CAP = 8;

function padPartNum(n, width = 2) {
  const text = String(n);
  return text.length >= width ? text : text.padStart(width, "0");
}

/**
 * Secondary Find queries for missing part numbers on an incomplete PartSet.
 * Styles: Part n/total, NofM, CDn / Disc n — capped.
 */
export function buildGapChaseQueries(set, { cap = GAP_CHASE_QUERY_CAP } = {}) {
  if (!set || set.complete || !(set.missing || []).length) return [];
  const base = String(set.title || set.base || "").trim();
  if (!base) return [];
  const total = set.total != null ? Number(set.total) : null;
  const style = set.style || "part";
  const queries = [];
  const seen = new Set();

  function add(q) {
    const key = String(q || "")
      .trim()
      .toLowerCase();
    if (!key || seen.has(key) || queries.length >= cap) return;
    seen.add(key);
    queries.push(String(q).trim());
  }

  for (const part of set.missing) {
    if (queries.length >= cap) break;
    const n = Number(part);
    if (!Number.isFinite(n)) continue;
    const padded = padPartNum(n);
    const totalPad = total != null ? padPartNum(total) : "";

    if (style === "cd") {
      add(`${base} CD${n}`);
      add(`${base} CD${padded}`);
      if (total) add(`${base} CD${n}/${total}`);
    } else if (style === "disc") {
      add(`${base} Disc ${n}`);
      if (total) add(`${base} Disc ${n}/${total}`);
      add(`${base} Disc ${padded}`);
    } else if (style === "of" && total) {
      add(`${base} ${padded}of${totalPad}`);
      add(`${base} ${n} of ${total}`);
      add(`${base} Part ${n}/${total}`);
    } else if (total) {
      add(`${base} Part ${n}/${total}`);
      add(`${base} Part ${n} of ${total}`);
      add(`${base} ${padded}of${totalPad}`);
    } else {
      add(`${base} Part ${n}`);
      add(`${base} CD${n}`);
    }
  }
  return queries.slice(0, cap);
}

/** Dedupe beyond hits by guid/title; returns merged list + how many were new. */
export function mergeBeyondHits(existing = [], incoming = []) {
  const byKey = new Map();
  for (const item of existing || []) {
    const key = item?.guid || item?.title;
    if (key) byKey.set(key, item);
  }
  let added = 0;
  for (const item of incoming || []) {
    const key = item?.guid || item?.title;
    if (!key || byKey.has(key)) continue;
    byKey.set(key, item);
    added += 1;
  }
  return { items: [...byKey.values()], added };
}

/**
 * After a chase, mark newly found formerly-missing parts as missingItems
 * so the CTA can say Request missing.
 */
export function annotateChasedGaps(set, priorMissing = []) {
  if (!set?.parts?.length) return set;
  const prior = new Set((priorMissing || []).map(Number).filter(Number.isFinite));
  if (!prior.size) {
    return { ...set, missingItems: set.missingItems || [] };
  }
  const foundGaps = set.parts.filter((row) => prior.has(Number(row.part))).map((row) => row.item);
  return {
    ...set,
    missingItems: foundGaps,
  };
}

export function partBeadStates(set) {
  if (!set || set.total == null || set.total < 1) return [];
  const have = new Set((set.parts || []).map((row) => Number(row.part)));
  const origin = partIndexOrigin(set.parts);
  const last = origin === 0 ? set.total - 1 : set.total;
  const beads = [];
  for (let i = origin; i <= last; i += 1) {
    beads.push({ part: i, state: have.has(i) ? "found" : "missing" });
  }
  return beads;
}
