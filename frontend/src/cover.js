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

export function jobChipLabel(status, role = "reader") {
  const map = {
    asked: "Asked",
    queued: "Queued",
    downloading: "Downloading",
    extracting: "Extracting",
    organized: "Open",
    review: "Review",
    failed: "Failed",
  };
  if (status && map[status]) return map[status];
  return role === "reader" ? "Ask the house" : "Request";
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
