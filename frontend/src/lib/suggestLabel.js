/**
 * Normalize typeahead display labels (UX-010).
 * Keeps the selected value as-is; only softens filename-like debris for display.
 */

const FILE_EXT = /\.(epub|pdf|mobi|azw3?|cbz|cbr|mp3|m4b|flac|nzb)$/i;

export function suggestDisplayLabel(raw) {
  let text = String(raw || "").trim();
  if (!text) return "";
  // Drop path prefixes when a suggestion looks like a dump path.
  if (text.includes("/") || text.includes("\\")) {
    const parts = text.split(/[/\\]/).filter(Boolean);
    text = parts[parts.length - 1] || text;
  }
  text = text.replace(FILE_EXT, "");
  // "(Born 1) - Born In Fire" → prefer the clean title after the dash when both sides match.
  const dashed = text.match(/^\([^)]+\)\s*[-–—]\s*(.+)$/);
  if (dashed) {
    const right = dashed[1].trim();
    if (right) return right;
  }
  return text.replace(/\s+/g, " ").trim() || String(raw || "").trim();
}
