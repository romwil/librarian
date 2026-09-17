import { queueReviewReasonCopy } from "./review.js";

const CLOTHS = [
  "#3a2a4a",
  "#1e2a3a",
  "#6b3a28",
  "#2c3d2e",
  "#5a1c22",
  "#3d2a18",
  "#8a7350",
  "#243044",
  "#3a2c18",
  "#4a2c22",
];

export function clothFor(title) {
  const text = String(title || "");
  let hash = 0;
  for (let i = 0; i < text.length; i += 1) {
    hash = (hash * 31 + text.charCodeAt(i)) >>> 0;
  }
  return CLOTHS[hash % CLOTHS.length];
}

export function shouldOpenPeek(event) {
  return !(event.metaKey || event.ctrlKey || event.shiftKey || event.altKey);
}

export function normalizeKind(kind) {
  if (kind === "gap") return "book";
  return kind || "book";
}

export function isSquareKind(kind) {
  return normalizeKind(kind) === "music";
}

export function isLandscapeKind(kind) {
  return normalizeKind(kind) === "audiobook";
}

export function coverKindClass(kind) {
  const k = normalizeKind(kind);
  if (k === "movie" || k === "tv" || k === "xxx") return "cover-book";
  return `cover-${k}`;
}

export function coverShapeClass(kind) {
  const k = normalizeKind(kind);
  if (k === "magazine") return "is-magazine";
  if (k === "comic") return "is-comic";
  if (k === "audiobook") return "is-landscape";
  if (k === "music") return "is-square";
  return "is-portrait";
}

export function coverClassNames(work, { art = false } = {}) {
  const kind = normalizeKind(work?.kind);
  const classes = ["cover", coverKindClass(kind), coverShapeClass(kind)];
  if (art) classes.push("has-art");
  if (work?.progress) classes.push("is-progress");
  if (work?.gap || work?.kind === "gap") classes.push("is-gap");
  if (kind === "music" && work?.music_state === "incoming") classes.push("is-incoming");
  return classes.filter(Boolean).join(" ");
}

export const JOB_HOUSEHOLD = {
  asked: "Asked",
  queued: "On the way",
  downloading: "On the way",
  extracting: "On the way",
  identifying: "On the way",
  organized: "Arrived",
  review: "Needs you",
  failed: "Failed",
};

const JOB_SAB_HINT = {
  queued: "Queued",
  downloading: "Downloading",
  extracting: "Extracting",
  identifying: "Identifying",
};

export function jobHouseholdLabel(status) {
  return JOB_HOUSEHOLD[status] || "";
}

export function isInboundJob(status) {
  return jobHouseholdLabel(status) === "On the way";
}

export function jobChipLabel(status, role = "reader") {
  return jobHouseholdLabel(status) || (role === "reader" ? "Ask the house" : "Request");
}

export function jobChipTone(status) {
  const label = jobHouseholdLabel(status);
  if (label === "Asked") return "is-asked";
  if (label === "Failed") return "is-failed";
  if (label === "Needs you") return "is-review";
  if (label === "On the way") return "is-transit";
  if (label === "Arrived") return "is-arrived";
  return "";
}

export function jobNeedsYouReason(job = {}) {
  if (job.status !== "review") return "";
  const fail = String(job.error || "").trim();
  if (fail) return fail;
  return queueReviewReasonCopy(job.review_reason);
}

export function jobQueueDetail(job = {}) {
  const payload = job.payload && typeof job.payload === "object" ? job.payload : {};
  const ingestSource = String(payload.source || "").trim();
  const path = String(job.storage_path || payload.path || "").trim();
  const nzo = String(job.nzo_id || "").trim();
  if (job.status === "review") {
    // Human reason is jobNeedsYouReason; keep NZB id / path as muted ops detail only.
    if (ingestSource === "ingest" || ingestSource === "watch") {
      return path;
    }
    return [path, nzo].filter(Boolean).join(" · ");
  }
  if (ingestSource === "ingest" || ingestSource === "watch") {
    const fail = String(job.error || "").trim();
    return [fail, path].filter(Boolean).join(" · ");
  }
  const sab = String(job.sab_status || "").trim();
  const fail = String(job.error || "").trim();
  if (job.status === "asked") return "Asked slip";
  if (job.status === "failed" && fail) return [fail, nzo].filter(Boolean).join(" · ");
  if (/grabbing|fetch nzb|wait\s+\d/i.test(sab)) {
    return [`Fetching NZB · ${sab}`, nzo].filter(Boolean).join(" · ");
  }
  if (sab) return [sab, nzo].filter(Boolean).join(" · ");
  const hint = String(fail || JOB_SAB_HINT[job.status] || "").trim();
  return [hint, nzo].filter(Boolean).join(" · ");
}

const RELEASE_NOISE =
  /\b(?:hybrid(?:\s*comic)?|comic\s*ebook|ebook|bitbook|web[- ]?dl|webrip|mp3|flac|m4b|m4a|nzb|par2|x264|x265|hevc|bluray|remux|repack|proper|internal)\b/gi;
const RELEASE_GROUP_TAIL = /-\s*[A-Za-z0-9]{2,16}$/;

export function isBeyondWork(work) {
  return Boolean(work?.beyond || (!work?.id && (work?.guid || work?.download_url)));
}

export function formatSize(size) {
  const n = Number(size);
  if (!Number.isFinite(n) || n <= 0) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(n < 10 * 1024 ? 1 : 0)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / (1024 * 1024)).toFixed(n < 10 * 1024 * 1024 ? 1 : 0)} MB`;
  return `${(n / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

export function formatPubAge(value) {
  if (!value) return "";
  const ms = Date.parse(value);
  if (!Number.isFinite(ms)) return "";
  const delta = Date.now() - ms;
  if (delta < 0) return "";
  const mins = Math.floor(delta / 60000);
  if (mins < 60) return mins <= 1 ? "1m" : `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 48) return `${hours}h`;
  const days = Math.floor(hours / 24);
  if (days < 60) return `${days}d`;
  const months = Math.floor(days / 30);
  if (months < 24) return `${months}mo`;
  return `${Math.floor(days / 365)}y`;
}

export function partHint(title = "") {
  const text = String(title || "");
  const numbered =
    text.match(/\[(\d+)\s*\/\s*(\d+)\]/) ||
    text.match(/\((\d+)\s*\/\s*(\d+)\)/) ||
    text.match(/\b(\d{1,3})\s*of\s*(\d{1,3})\b/i);
  if (numbered) return `${Number(numbered[1])}/${Number(numbered[2])}`;
  const named = text.match(/\b(?:part|cd|disc|disk)\s*(\d{1,3})\b/i);
  if (named) return `p${Number(named[1])}`;
  return "";
}

export function humanizeReleaseTitle(title = "") {
  const raw = String(title || "").trim();
  if (!raw) return "";
  const dotCount = (raw.match(/\./g) || []).length;
  const looksRelease = /[._]{2,}|\.-+\.|_/.test(raw) || dotCount >= 3;
  if (!looksRelease) return raw;
  let text = raw;
  text = text.replace(/\.-+\.?/g, " - ");
  text = text.replace(/[._]+/g, " ");
  text = text.replace(RELEASE_NOISE, " ");
  text = text.replace(RELEASE_GROUP_TAIL, "");
  text = text.replace(/\s*[-–—|:]\s*$/g, "");
  text = text.replace(/\s{2,}/g, " ").trim();
  return text || raw;
}

export function coverDisplayTitle(work) {
  if (!work) return "Untitled";
  const preferred = work.book_title || work.series_name || work.title || "";
  if (isBeyondWork(work) || /[._]{2,}|\.-+\./.test(preferred)) {
    return humanizeReleaseTitle(preferred) || preferred || "Untitled";
  }
  return preferred || "Untitled";
}

export function coverTip(work) {
  if (!work) return "";
  return [
    coverDisplayTitle(work),
    formatSize(work.size),
    formatPubAge(work.pub_date),
    String(work.host_name || "").trim(),
    partHint(work.title) ? `Part ${partHint(work.title)}` : "",
  ]
    .filter(Boolean)
    .join(" · ");
}

function beyondByline(work, fallback = "") {
  const kind = normalizeKind(work?.kind);
  const bits = [
    kind && kind !== "book" ? kind : "",
    formatSize(work?.size),
    formatPubAge(work?.pub_date),
    partHint(work?.title) ? `Part ${partHint(work.title)}` : "",
  ].filter(Boolean);
  return bits.join(" · ") || fallback;
}

export function coverOverlay(work) {
  const kind = normalizeKind(work?.kind);
  const beyond = isBeyondWork(work);
  const title = coverDisplayTitle(work);
  if (kind === "magazine") {
    return {
      title,
      byline: beyond ? beyondByline(work, work.author || work.series_name || "Magazine") : work.author || work.series_name || "Magazine",
      chip: work.series_index || work.year || "",
    };
  }
  if (kind === "comic") {
    const series = work.series_name ? coverDisplayTitle({ ...work, title: work.series_name }) : title;
    return {
      title: series,
      byline: beyond
        ? beyondByline(work, "Comic")
        : work.series_name && work.title && work.title !== work.series_name
          ? work.title
          : work.author || "Comic",
      chip: work.series_index ? `#${work.series_index}` : beyond ? "" : work.year || "",
    };
  }
  if (kind === "audiobook") {
    const parts = work.parts || work.series_index;
    const duration = work.duration || work.runtime;
    const part = partHint(work?.title);
    return {
      title,
      byline: beyond ? beyondByline(work, work.author || "Audiobook") : work.author || "Audiobook",
      chip:
        [duration, parts ? `${parts} parts` : "", part ? `Part ${part}` : ""].filter(Boolean).join(" · ") ||
        (beyond ? "" : "Listen"),
    };
  }
  if (kind === "music") {
    return {
      title,
      byline: beyond ? beyondByline(work, work.author || work.artist || "Album") : work.author || work.artist || "Album",
      chip: work.music_state === "incoming" ? "Incoming" : beyond ? "" : "Library",
    };
  }
  if (kind === "movie" || kind === "tv" || kind === "xxx") {
    return {
      title,
      byline: beyond ? beyondByline(work, kind) : kind,
      chip: "",
    };
  }
  return {
    title,
    byline: beyond ? beyondByline(work, work?.author || "Book") : work?.author || "Book",
    chip: "",
  };
}

export function coverCaption(work) {
  if (!work) return "";
  if (isBeyondWork(work)) {
    const bits = [coverDisplayTitle(work), formatSize(work.size), formatPubAge(work.pub_date)].filter(Boolean);
    return bits.join(" · ") || coverDisplayTitle(work);
  }
  if (work.kind === "magazine") {
    return work.series_index || work.year || work.title || "";
  }
  if (work.kind === "comic") {
    return [work.series_name, work.series_index].filter(Boolean).join(" #") || work.title || "";
  }
  if (work.kind === "audiobook") {
    return [work.title, work.duration || work.runtime].filter(Boolean).join(" · ") || "Untitled";
  }
  if (work.kind === "music") {
    return work.music_state === "incoming" ? `${work.title || "Album"} · incoming` : work.title || "Untitled";
  }
  return work.title || "Untitled";
}

/** Prefer local cover; fall back to indexer/remote cover URL for hero/peek wash. */
export function coverWashUrl(work) {
  if (!work) return "";
  if (work.has_cover && work.id) return `/api/works/${work.id}/cover`;
  const remote = String(work.cover || work.cover_url || "").trim();
  return remote;
}

/** CSS custom-property style for `--work-wash`, or undefined when no art. */
export function coverWashStyle(work) {
  const url = coverWashUrl(work);
  if (!url) return undefined;
  const safe = url.replace(/\\/g, "\\\\").replace(/"/g, '\\"');
  return { "--work-wash": `url("${safe}")` };
}
