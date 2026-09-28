/** Ingest preview map helpers — warm presence, never a KPI strip. */

const COUNT_WORDS = {
  1: "One",
  2: "Two",
  3: "Three",
  4: "Four",
  5: "Five",
  6: "Six",
  7: "Seven",
  8: "Eight",
  9: "Nine",
  10: "Ten",
  11: "Eleven",
  12: "Twelve",
};

export function ingestPreviewPresence(preview) {
  const fromServer = String(preview?.presence || "").trim();
  if (fromServer) return fromServer;
  const n = Math.max(0, Number(preview?.volumes_found) || 0);
  if (n < 1) return "Nothing to shelve here — empty or only junk.";
  if (n === 1) return "One volume waits on the map.";
  const word = COUNT_WORDS[n];
  if (word) return `${word} volumes wait on the map.`;
  return `${n} volumes wait on the map.`;
}

export function ingestPreviewIsEmpty(preview) {
  if (!preview) return true;
  if (preview.empty === true) return true;
  return (Number(preview.volumes_found) || 0) < 1;
}

export function ingestPreviewVolumes(preview) {
  return Array.isArray(preview?.volumes) ? preview.volumes : [];
}

export function volumeStem(volume) {
  return String(volume?.stem || volume?.title || "Untitled").trim() || "Untitled";
}

export function volumeKindLabel(volume) {
  const label = String(volume?.kind_label || "").trim();
  if (label) return label;
  const kind = String(volume?.kind || "").trim();
  if (!kind) return "Unknown";
  return kind.charAt(0).toUpperCase() + kind.slice(1);
}

export function volumeIsTwin(volume) {
  return Boolean(volume?.twin || volume?.role === "twin");
}
