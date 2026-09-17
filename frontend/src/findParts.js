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
const NOISE_PREFIX = /^(?:attn\s+\S+\s+|nmr(?:t)?\s+|\[?[a-z0-9]{6,}\]\s*-?\s*)/i;

export function parsePartMarker(title = "") {
  const text = String(title || "");
  if (!text.trim()) return null;

  const bracket = text.match(BRACKET_PART);
  if (bracket) {
    return {
      part: Number(bracket[1]),
      total: Number(bracket[2]),
      style: "bracket",
      raw: bracket[0],
    };
  }

  const paren = text.match(PAREN_PART);
  if (paren) {
    return {
      part: Number(paren[1]),
      total: Number(paren[2]),
      style: "paren",
      raw: paren[0],
    };
  }

  const ofMatch = text.match(OF_PART);
  if (ofMatch) {
    return {
      part: Number(ofMatch[1]),
      total: Number(ofMatch[2]),
      style: "of",
      raw: ofMatch[0],
    };
  }

  const named = text.match(NAMED_PART);
  if (named) {
    const total = named[2] ? Number(named[2]) : null;
    return {
      part: Number(named[1]),
      total,
      style: named[0].toLowerCase().startsWith("cd")
        ? "cd"
        : named[0].toLowerCase().startsWith("disc") || named[0].toLowerCase().startsWith("disk")
          ? "disc"
          : "part",
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

  const honesty =
    gapCount > 0
      ? `Missing ${gapCount} part${gapCount === 1 ? "" : "s"} aren’t listed in these indexer results — refine the search or try another host.`
      : "Indexer only returned some parts — missing NZBs can’t be requested from this result.";

  return {
    kind: "listed-only",
    style: "secondary",
    label: n > 0 ? `Request listed (${n})` : "Request listed",
    enabled: n > 0,
    honesty,
  };
}
