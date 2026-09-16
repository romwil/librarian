/** Browse /data (or DATA_DIR in tests) without treating hidden junk as a volume. */

export const SKIPPED_BROWSE_NAMES = new Set([".ds_store", "thumbs.db", "desktop.ini"]);

export function isSkippedBrowseName(name) {
  const text = String(name || "");
  if (!text || text.startsWith(".") || text.startsWith("._")) return true;
  return SKIPPED_BROWSE_NAMES.has(text.toLowerCase());
}

export function filterBrowseEntries(entries = []) {
  return (entries || []).filter((entry) => !isSkippedBrowseName(entry?.name));
}

export function ingestSourcePath(job = {}) {
  const payload = job.payload && typeof job.payload === "object" ? job.payload : {};
  const source = String(payload.source || "").trim();
  if (source !== "ingest" && source !== "watch") return "";
  return String(job.storage_path || payload.path || "").trim();
}
