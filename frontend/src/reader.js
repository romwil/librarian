export const READABLE_KINDS = ["book", "magazine", "comic"];
export const READING_EXTS = [".epub", ".cbz", ".pdf"];

const EXT_RANK = { ".epub": 0, ".cbz": 1, ".pdf": 2 };

export function fileExtension(name) {
  const text = String(name || "")
    .trim()
    .toLowerCase()
    .replace(/\\/g, "/");
  const base = text.slice(text.lastIndexOf("/") + 1);
  const dot = base.lastIndexOf(".");
  return dot >= 0 ? base.slice(dot) : "";
}

function fileLabel(row) {
  return String(row?.filename || row?.path || "");
}

function isOnDisk(row) {
  return row?.on_disk !== false;
}

export function readingFiles(files = []) {
  return [...(files || [])]
    .filter((row) => isOnDisk(row) && READING_EXTS.includes(fileExtension(fileLabel(row))))
    .sort((left, right) => {
      const leftExt = fileExtension(fileLabel(left));
      const rightExt = fileExtension(fileLabel(right));
      const rank = (EXT_RANK[leftExt] ?? 9) - (EXT_RANK[rightExt] ?? 9);
      if (rank) return rank;
      return fileLabel(left).localeCompare(fileLabel(right));
    });
}

export function primaryReadingFile(files = []) {
  const tagged = (files || []).find((row) => row?.reading_room && isOnDisk(row));
  if (tagged && READING_EXTS.includes(fileExtension(fileLabel(tagged)))) return tagged;
  return readingFiles(files)[0] || null;
}

export function canReadInApp(work, files = []) {
  if (!READABLE_KINDS.includes(work?.kind)) return false;
  return Boolean(primaryReadingFile(files));
}

/** Kindle-only (and similar) stay on Download — not an inline Open. */
export function canOpenInlineMedia(work, canDownload = false, canRead = false) {
  if (canRead) return false;
  if (!canDownload) return false;
  return !READABLE_KINDS.includes(work?.kind);
}

export function readerEngine(files = []) {
  const ext = fileExtension(fileLabel(primaryReadingFile(files)));
  if (ext === ".pdf") return "pdf";
  if (ext === ".cbz") return "cbz";
  if (ext === ".epub") return "epub";
  return "";
}

export function workReaderPath(workId) {
  return `/works/${encodeURIComponent(workId)}?read=1`;
}

export function filenameFromDisposition(header, fallback = "volume") {
  const text = String(header || "");
  const star = /filename\*=(?:UTF-8'')?([^;]+)/i.exec(text);
  if (star) {
    try {
      return decodeURIComponent(star[1].trim().replace(/^"+|"+$/g, ""));
    } catch {
      return star[1].trim();
    }
  }
  const plain = /filename="([^"]+)"/i.exec(text) || /filename=([^;]+)/i.exec(text);
  if (plain) return plain[1].trim().replace(/^"+|"+$/g, "");
  return fallback;
}

export function readingFileName(files = [], header = "") {
  const fromFiles = fileLabel(primaryReadingFile(files));
  if (fromFiles) return fromFiles.split("/").pop();
  return filenameFromDisposition(header, "volume");
}

export function readerOpenError(error, responseStatus = 0) {
  const raw = String(error?.message || error || "").trim();
  if (responseStatus === 422 || /isn.?t a readable EPUB/i.test(raw)) {
    return "This file isn’t a readable EPUB, CBZ, or PDF.";
  }
  if (/container|corrupt|zip|EPUBJS|failed to load/i.test(raw)) {
    return "This file isn’t a readable EPUB/CBZ/PDF, or the EPUB on disk looks damaged.";
  }
  return raw || "This volume could not be opened in the reading room.";
}
