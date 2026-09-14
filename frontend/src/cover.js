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

export function isSquareKind(kind) {
  return kind === "music" || kind === "audiobook";
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

export function coverCaption(work) {
  if (!work) return "";
  if (work.kind === "magazine") {
    return work.series_index || work.year || work.title || "";
  }
  if (work.kind === "comic") {
    return [work.series_name, work.series_index].filter(Boolean).join(" #") || work.title || "";
  }
  return work.title || "Untitled";
}
