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
  return `cover-${normalizeKind(kind)}`;
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

export function jobQueueDetail(job = {}) {
  const payload = job.payload && typeof job.payload === "object" ? job.payload : {};
  const ingestSource = String(payload.source || "").trim();
  const path = String(job.storage_path || payload.path || "").trim();
  if (ingestSource === "ingest" || ingestSource === "watch") {
    const fail = String(job.error || "").trim();
    return [fail, path].filter(Boolean).join(" · ");
  }
  const nzo = String(job.nzo_id || "").trim();
  const sab = String(job.sab_status || "").trim();
  const fail = String(job.error || "").trim();
  if (job.status === "asked") return "Asked slip";
  if (job.status === "failed" && fail) return [fail, nzo].filter(Boolean).join(" · ");
  if (sab) return [sab, nzo].filter(Boolean).join(" · ");
  const hint = String(fail || JOB_SAB_HINT[job.status] || "").trim();
  return [hint, nzo].filter(Boolean).join(" · ");
}

export function coverOverlay(work) {
  const kind = normalizeKind(work?.kind);
  const title = work?.title || "Untitled";
  if (kind === "magazine") {
    return {
      title,
      byline: work.author || work.series_name || "Magazine",
      chip: work.series_index || work.year || "",
    };
  }
  if (kind === "comic") {
    const series = work.series_name || title;
    return {
      title: series,
      byline: work.series_name && title !== work.series_name ? title : work.author || "Comic",
      chip: work.series_index ? `#${work.series_index}` : work.year || "",
    };
  }
  if (kind === "audiobook") {
    const parts = work.parts || work.series_index;
    const duration = work.duration || work.runtime;
    return {
      title,
      byline: work.author || "Audiobook",
      chip: [duration, parts ? `${parts} parts` : ""].filter(Boolean).join(" · ") || "Listen",
    };
  }
  if (kind === "music") {
    return {
      title,
      byline: work.author || work.artist || "Album",
      chip: work.music_state === "incoming" ? "Incoming" : "Library",
    };
  }
  return {
    title,
    byline: work?.author || "Book",
    chip: "",
  };
}

export function coverCaption(work) {
  if (!work) return "";
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
