/** PDF.js helpers. The worker stays a same-origin hashed asset (`script-src 'self'`). */

/** Bytes per HTTP range. 64KB default + streaming from byte 0 storms a 400MB comic. */
export const PDF_RANGE_CHUNK_SIZE = 2 * 1024 * 1024;

/**
 * 2MB ranges plus a progressive stream. `disableStream: true` alone made pdf.js
 * fire every chunk at once (ObjectLoader fallback) and miss the open timeout.
 */
export const PDF_LOAD_OPTIONS = {
  withCredentials: true,
  httpHeaders: { "X-Librarian": "1" },
  isEvalSupported: false,
  disableAutoFetch: true,
  disableStream: false,
  disableRange: false,
  rangeChunkSize: PDF_RANGE_CHUNK_SIZE,
  verbosity: 0,
};

export function pdfPageFromPosition(position, pageCount = 0) {
  const n = Number.parseInt(String(position || ""), 10);
  if (!Number.isFinite(n) || n < 1) return 1;
  const count = Number(pageCount) || 0;
  if (count > 0 && n > count) return count;
  return n;
}

export function pdfPersistDetail(page, pageCount) {
  const count = Math.max(1, Number(pageCount) || 1);
  const current = Math.min(count, Math.max(1, Number(page) || 1));
  return { cfi: String(current), fraction: current / count };
}

function pageLabel(page, pageCount) {
  return `Page ${page} of ${pageCount}`;
}

function fitScale(unscaled, box, dpr) {
  const width = Number(box?.width) || 0;
  const height = Number(box?.height) || 0;
  if (!(width > 0) || !(height > 0) || !(unscaled.width > 0) || !(unscaled.height > 0)) {
    return Math.max(dpr, 1);
  }
  return Math.max(0.25, Math.min(width / unscaled.width, height / unscaled.height) * dpr);
}

export async function openPdfVolume({
  url,
  container,
  position = "",
  onRelocate,
  onProgress,
  signal,
} = {}) {
  if (!container) throw new Error("This volume could not be opened in the reading room.");
  const pdfjs = await import("pdfjs-dist");
  const workerMod = await import("pdfjs-dist/build/pdf.worker.min.mjs?url");
  pdfjs.GlobalWorkerOptions.workerSrc = workerMod.default;
  const task = pdfjs.getDocument({
    url,
    ...PDF_LOAD_OPTIONS,
  });
  if (onProgress) {
    task.onProgress = (evt) => onProgress(evt);
  }
  const abort = () => {
    try {
      task.destroy();
    } catch {
      /* already gone */
    }
  };
  if (signal) {
    if (signal.aborted) {
      abort();
      throw Object.assign(new Error("This volume took too long to open."), { name: "AbortError", status: 504 });
    }
    signal.addEventListener("abort", abort, { once: true });
  }
  const pdf = await task.promise;
  if (signal?.aborted) {
    abort();
    throw Object.assign(new Error("This volume took too long to open."), { name: "AbortError", status: 504 });
  }

  const wrap = document.createElement("div");
  wrap.className = "reader-pdf";
  const canvas = document.createElement("canvas");
  canvas.setAttribute("role", "img");
  wrap.appendChild(canvas);
  container.replaceChildren(wrap);

  let pageNum = pdfPageFromPosition(position, pdf.numPages);
  let renderToken = 0;
  let closed = false;

  async function show(page) {
    if (closed) return;
    const wanted = pdfPageFromPosition(page, pdf.numPages);
    const token = ++renderToken;
    const pdfPage = await pdf.getPage(wanted);
    if (closed || token !== renderToken) return;
    const unscaled = pdfPage.getViewport({ scale: 1 });
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const scale = fitScale(unscaled, container.getBoundingClientRect(), dpr);
    const viewport = pdfPage.getViewport({ scale });
    canvas.width = Math.max(1, Math.floor(viewport.width));
    canvas.height = Math.max(1, Math.floor(viewport.height));
    canvas.style.width = `${canvas.width / dpr}px`;
    canvas.style.height = `${canvas.height / dpr}px`;
    canvas.setAttribute("aria-label", pageLabel(wanted, pdf.numPages));
    await pdfPage.render({ canvasContext: canvas.getContext("2d", { alpha: false }), viewport }).promise;
    if (closed || token !== renderToken) return;
    pageNum = wanted;
    onRelocate?.(pdfPersistDetail(pageNum, pdf.numPages));
  }

  await show(pageNum);

  const observer = new ResizeObserver(() => {
    void show(pageNum);
  });
  observer.observe(container);

  return {
    goLeft() {
      if (pageNum <= 1) return false;
      void show(pageNum - 1);
      return true;
    },
    goRight() {
      if (pageNum >= pdf.numPages) return false;
      void show(pageNum + 1);
      return true;
    },
    close() {
      closed = true;
      observer.disconnect();
      abort();
      wrap.remove();
    },
  };
}
