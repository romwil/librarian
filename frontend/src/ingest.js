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

/** Status line vs alert for Add to the shelves after POST /api/ingest. */
export function ingestResultMessage(job = {}, path = "") {
  const title = String(job.title || path || "").trim() || "volume";
  const status = String(job.status || "").trim();
  if (status === "failed") {
    const reason = String(job.error || "").trim();
    return {
      kind: "error",
      text: reason || `Failed — ${title}`,
    };
  }
  const word =
    status === "organized"
      ? "Arrived"
      : status === "review"
        ? "Needs you"
        : "On the way";
  return { kind: "status", text: `${word} — ${title}` };
}
