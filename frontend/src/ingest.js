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

export function ingestIsRunning(status) {
  return String(status?.status || "") === "running";
}

/** Household progress line for Add to the shelves polling. */
export function ingestProgressSummary(status) {
  if (!status || typeof status !== "object") return "";
  const state = String(status.status || "");
  if (state === "idle") return "";
  if (state === "failed") return status.error || "Shelving failed.";
  const done = Number(status.done || 0);
  const total = Number(status.total || 0);
  const shelved = Number(status.shelved || 0);
  const review = Number(status.review || 0);
  const skipped = Number(status.skipped || 0);
  const title = String(status.current_title || "").trim();
  const phase = String(status.phase || "").trim();
  if (state === "completed") {
    const result = status.result || {};
    const s = Number(result.shelved != null ? result.shelved : shelved);
    const r = Number(result.review != null ? result.review : review);
    const k = Number(result.skipped != null ? result.skipped : skipped);
    const parts = [];
    if (s) parts.push(`shelved ${s}`);
    if (r) parts.push(`needs you ${r}`);
    if (k) parts.push(`skipped ${k}`);
    if (!parts.length) return "Finished looking.";
    return `Finished — ${parts.join(", ")}`;
  }
  const phaseWord =
    phase === "scanning"
      ? "Scanning"
      : phase === "identifying"
        ? "Identifying"
        : phase === "organizing"
          ? "Organizing"
          : "Shelving";
  const count = total > 0 ? `${done} of ${total}` : done ? `${done} done` : "";
  const head = [phaseWord, count].filter(Boolean).join(" · ");
  const tallies = [];
  if (shelved) tallies.push(`shelved ${shelved}`);
  if (review) tallies.push(`needs you ${review}`);
  if (skipped) tallies.push(`skipped ${skipped}`);
  const mid = tallies.length ? ` · ${tallies.join(" · ")}` : "";
  const tail = title ? ` · ${title}` : "";
  return `${head}${mid}${tail}` || "Adding…";
}

export function ingestPhaseLabel(phase) {
  const key = String(phase || "").trim();
  if (key === "scanning") return "scanning";
  if (key === "identifying") return "identifying";
  if (key === "organizing") return "organizing";
  if (key === "done") return "done";
  if (key === "failed") return "failed";
  return key || "shelving";
}
