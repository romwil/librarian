export const READABLE_KINDS = ["book", "magazine", "comic"];
export const READING_EXTS = [".epub", ".cbz", ".pdf"];

/** Paper under Foliate pages — Reading Room chrome stays dark; page text stays light. */
export const EPUB_PAGE_SURFACE = "#faf6ee";

/**
 * Injected via foliate-view renderer.setStyles. Foliate clears body bg onto its
 * #background layer; --theme-bg-color replaces a dark/transparent extracted page
 * so OS dark mode cannot show Reading Room chrome through text pages.
 */
export const EPUB_READER_STYLES = `
html {
  color-scheme: only light;
  --theme-bg-color: ${EPUB_PAGE_SURFACE};
}
body {
  margin: 0;
  line-height: 1.65;
  font-size: 1.05rem;
  letter-spacing: 0.01em;
  hyphens: auto;
}
p, li {
  max-width: 38rem;
}
`;

/** Left / right thirds → page turn; middle stays free for selection. */
export function pageTurnSide(clientX, width, { left = 1 / 3, right = 2 / 3 } = {}) {
  if (!(width > 0) || !Number.isFinite(clientX)) return "";
  const ratio = clientX / width;
  if (ratio < left) return "left";
  if (ratio > right) return "right";
  return "";
}

/**
 * Turn target for a viewport x against a box (stage letterbox or page image).
 * `clientX` is viewport space; `box.left` is that box's viewport origin.
 * A centered cover's left edge is not the stage's left edge.
 */
export function pageTurnTarget(clientX, box) {
  if (!box) return "";
  const origin = Number(box.left);
  const width = Number(box.width);
  if (!Number.isFinite(origin) || !(width > 0)) return "";
  return pageTurnSide(clientX - origin, width);
}

/**
 * Comic tap. The black stage edges use the host surface. A tap that misses
 * those thirds can still land on the image's own edge.
 */
export function comicTurnSide(clientX, stageBox, imageBox) {
  const stageSide = pageTurnTarget(clientX, stageBox);
  if (stageSide) return stageSide;
  return pageTurnTarget(clientX, imageBox);
}

/** Reflowable prose scrolls. Comics, fixed-layout pages, and PDF keep a page surface. */
export function readerFlow(engine, fixedLayout = false) {
  if (fixedLayout || engine === "cbz" || engine === "pdf") return "";
  if (engine === "epub") return "scrolled";
  return "";
}

/** One comic image per view. A landscape spread parks the cover on the right and a blank page on the left. */
export function comicSpreadMode(book) {
  if (!book) return book;
  const rendition = book.rendition || {};
  book.rendition = {
    ...rendition,
    layout: rendition.layout || "pre-paginated",
    spread: "none",
  };
  return book;
}

/** Header hint. Prose can scroll; a comic only turns. */
export function readerChromeHint(engine) {
  if (engine === "epub") return "Scroll to read · edges or ← → turn · Esc closes";
  return "Edges or ← → turn · Esc closes";
}

/** Left / right page turn. A center tap does not move. */
export function turnReaderPage(view, side) {
  if (side === "left") return view?.goLeft?.() ?? false;
  if (side === "right") return view?.goRight?.() ?? false;
  return false;
}

/** Pixel delta from a wheel or trackpad tick. Pinch-zoom (ctrl) stays with the browser. */
export function readerWheelDelta(event) {
  if (!event || event.ctrlKey) return 0;
  const y = Number(event.deltaY) || 0;
  const x = Number(event.deltaX) || 0;
  const raw = Math.abs(y) >= Math.abs(x) ? y : x;
  if (!raw) return 0;
  if (event.deltaMode === 1) return raw * 16;
  if (event.deltaMode === 2) return raw * 800;
  return raw;
}

/**
 * Move a scrolled Foliate renderer by `delta` pixels.
 * At the edge of a section, hand the tick to the next or previous spine item
 * so a long book does not stop at the chapter break.
 */
export function scrollReader(renderer, delta) {
  if (!renderer || !Number.isFinite(delta) || delta === 0) return false;
  if (typeof renderer.containerPosition !== "number") return false;
  const start = Number.isFinite(renderer.start) ? renderer.start : Math.abs(renderer.containerPosition);
  const size = Number.isFinite(renderer.size) ? renderer.size : 0;
  const viewSize = Number.isFinite(renderer.viewSize) ? renderer.viewSize : 0;
  if (size > 0 && viewSize > 0) {
    const max = Math.max(0, viewSize - size);
    if (delta > 0 && start >= max - 1) {
      if (renderer.atEnd) return false;
      renderer.next?.();
      return true;
    }
    if (delta < 0 && start <= 1) {
      if (renderer.atStart) return false;
      renderer.prev?.();
      return true;
    }
  }
  renderer.containerPosition += delta;
  return true;
}

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
  const tagged = readingFiles((files || []).filter((row) => row?.reading_room));
  if (tagged.length) return tagged[0];
  return readingFiles(files)[0] || null;
}

/** Pick a specific catalog file for the Reading Room, else the primary. */
export function chooseReadingFile(files = [], fileId = "") {
  const wanted = String(fileId || "").trim();
  if (wanted) {
    const match = (files || []).find((row) => String(row?.id || "") === wanted && isOnDisk(row));
    if (match && READING_EXTS.includes(fileExtension(fileLabel(match)))) return match;
  }
  return primaryReadingFile(files);
}

export function canReadInApp(work, files = []) {
  if (!READABLE_KINDS.includes(work?.kind)) return false;
  return Boolean(primaryReadingFile(files));
}

/** Kindle-only (and similar) stay on Download — not an inline Read.
 *  Audiobooks use Listen (Phase 2b), not a raw inline Read. */
export function canOpenInlineMedia(work, canDownload = false, canRead = false) {
  if (canRead) return false;
  if (!canDownload) return false;
  if (work?.kind === "audiobook") return false;
  return !READABLE_KINDS.includes(work?.kind);
}

/** In-browser reader CTA for books/comics/mags — never Listen. */
export function readerCtaLabel(work) {
  if (work?.kind === "audiobook" || work?.kind === "music") return "";
  return "Read";
}

export function readerEngine(files = [], fileId = "") {
  const ext = fileExtension(fileLabel(chooseReadingFile(files, fileId)));
  if (ext === ".pdf") return "pdf";
  if (ext === ".cbz") return "cbz";
  if (ext === ".epub") return "epub";
  return "";
}

export function workReaderPath(workId, fileId = "") {
  const base = `/works/${encodeURIComponent(workId)}?read=1`;
  const wanted = String(fileId || "").trim();
  return wanted ? `${base}&file=${encodeURIComponent(wanted)}` : base;
}

export function workDownloadUrl(workId, { inline = false, fileId = "" } = {}) {
  const params = new URLSearchParams();
  if (inline) params.set("inline", "1");
  const wanted = String(fileId || "").trim();
  if (wanted) params.set("file", wanted);
  const qs = params.toString();
  return `/api/works/${encodeURIComponent(workId)}/download${qs ? `?${qs}` : ""}`;
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

export function readingFileName(files = [], header = "", fileId = "") {
  const fromFiles = fileLabel(chooseReadingFile(files, fileId));
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
