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
        : status === "skipped"
          ? "Ignored duplicate"
          : "On the way";
  return { kind: "status", text: `${word} — ${title}` };
}

export function ingestIsRunning(status) {
  return String(status?.status || "") === "running";
}

/** True when POST /api/ingest returned the live progress blob (not a single job). */
export function ingestLooksLikeProgress(payload) {
  if (!payload || typeof payload !== "object") return false;
  if (Object.prototype.hasOwnProperty.call(payload, "kicked_off")) return true;
  if (Object.prototype.hasOwnProperty.call(payload, "phase")) return true;
  if (Object.prototype.hasOwnProperty.call(payload, "done") && Object.prototype.hasOwnProperty.call(payload, "total")) {
    return true;
  }
  return false;
}

/** Legacy `{ job }` responses only — never treat an empty `{}` as a job. */
export function ingestLegacyJob(payload) {
  if (ingestLooksLikeProgress(payload)) return null;
  const job = payload?.job;
  if (!job || typeof job !== "object") return null;
  if (!job.status && !job.id) return null;
  return job;
}

/** 0–100 for the shelving meter; null when total is unknown. */
export function ingestProgressPercent(status) {
  if (!status || typeof status !== "object") return null;
  const total = Number(status.total || 0);
  if (total <= 0) return null;
  const done = Number(status.done || 0);
  if (!Number.isFinite(done)) return null;
  return Math.max(0, Math.min(100, Math.round((done / total) * 100)));
}

function _num(value, fallback = 0) {
  const n = Number(value);
  return Number.isFinite(n) ? n : fallback;
}

/** Pull tallies from live progress or completed result. */
export function ingestProgressTallies(status) {
  if (!status || typeof status !== "object") {
    return { seen: 0, shelved: 0, review: 0, skipped: 0, duplicates: 0, errors: 0, volumes: 0, files: 0 };
  }
  const result = status.result && typeof status.result === "object" ? status.result : {};
  const pick = (key) => {
    if (result[key] != null) return _num(result[key]);
    return _num(status[key]);
  };
  const seen = pick("seen") || pick("done");
  return {
    seen,
    shelved: pick("shelved"),
    review: pick("review"),
    skipped: pick("skipped"),
    duplicates: pick("duplicates"),
    errors: pick("errors"),
    volumes: pick("volumes_found") || pick("total"),
    files: pick("files_found"),
  };
}

/** Depth-friendly path for deep Calibre trees — keep leaf + a parent or two. */
export function ingestDisplayPath(path, { maxSegments = 4 } = {}) {
  const text = String(path || "").trim();
  if (!text) return "";
  const parts = text.split(/[/\\]+/).filter(Boolean);
  if (parts.length <= maxSegments) return text.startsWith("/") ? `/${parts.join("/")}` : parts.join("/");
  const keep = parts.slice(-maxSegments);
  return `…/${keep.join("/")}`;
}

/** Household progress line for Add to the shelves polling. */
export function ingestProgressSummary(status) {
  if (!status || typeof status !== "object") return "";
  const state = String(status.status || "");
  if (state === "idle") return "";
  if (state === "failed") return status.error || "Shelving failed.";
  const tallies = ingestProgressTallies(status);
  const title = String(status.current_title || "").trim();
  const phase = String(status.phase || "").trim();
  const pct = ingestProgressPercent(status);
  const done = _num(status.done);
  const total = _num(status.total);

  if (state === "completed") {
    const parts = [];
    parts.push(`seen ${tallies.seen || total || done}`);
    parts.push(`added ${tallies.shelved}`);
    if (tallies.duplicates) parts.push(`ignored duplicates ${tallies.duplicates}`);
    if (tallies.review) parts.push(`needs you ${tallies.review}`);
    if (tallies.skipped) parts.push(`skipped ${tallies.skipped}`);
    if (tallies.errors) parts.push(`failed ${tallies.errors}`);
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

  if (phase === "scanning" && total <= 0) {
    const found = [];
    if (tallies.volumes) found.push(`${tallies.volumes} volume${tallies.volumes === 1 ? "" : "s"}`);
    if (tallies.files) found.push(`${tallies.files} file${tallies.files === 1 ? "" : "s"}`);
    if (tallies.duplicates) found.push(`${tallies.duplicates} duplicate${tallies.duplicates === 1 ? "" : "s"}`);
    const foundBit = found.length ? ` · found ${found.join(" · ")}` : "";
    const tail = title ? ` · ${title}` : "";
    return `${phaseWord}${foundBit}${tail}` || "Scanning…";
  }

  const count = total > 0 ? `${done} of ${total}` : done ? `${done} done` : "";
  const pctBit = pct != null ? `${pct}%` : "";
  const head = [phaseWord, count, pctBit].filter(Boolean).join(" · ");
  const midParts = [];
  if (tallies.shelved) midParts.push(`added ${tallies.shelved}`);
  if (tallies.duplicates) midParts.push(`duplicates ${tallies.duplicates}`);
  if (tallies.review) midParts.push(`needs you ${tallies.review}`);
  if (tallies.skipped) midParts.push(`skipped ${tallies.skipped}`);
  const mid = midParts.length ? ` · ${midParts.join(" · ")}` : "";
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

/** Multi-line completion / live tallies for the progress panel. */
export function ingestTallyLines(status) {
  const tallies = ingestProgressTallies(status);
  const state = String(status?.status || "");
  const lines = [];
  if (state === "completed" || tallies.seen || tallies.shelved || tallies.duplicates) {
    if (tallies.seen || state === "completed") lines.push(`Seen ${tallies.seen}`);
    lines.push(`Added ${tallies.shelved}`);
    if (tallies.duplicates || state === "completed") lines.push(`Ignored duplicates ${tallies.duplicates}`);
    if (tallies.review) lines.push(`Needs you ${tallies.review}`);
    if (tallies.skipped) lines.push(`Skipped ${tallies.skipped}`);
    if (tallies.errors) lines.push(`Failed ${tallies.errors}`);
  }
  if (state === "running" && String(status?.phase || "") === "scanning") {
    if (tallies.volumes) lines.unshift(`Found ${tallies.volumes} volumes`);
    if (tallies.files) lines.splice(1, 0, `${tallies.files} media files`);
  }
  return lines;
}
