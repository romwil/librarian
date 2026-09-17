import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { humanError } from "../copy.js";
import {
  EPUB_READER_STYLES,
  pageTurnSide,
  readerEngine,
  readerOpenError,
  readingFileName,
  workDownloadUrl,
} from "../reader.js";

export default function Reader({ work, files = [], fileId = "", progress = null, onClose }) {
  const stage = useRef(null);
  const viewRef = useRef(null);
  const lastLoc = useRef(null);
  const persistTimer = useRef(0);
  const [status, setStatus] = useState("Opening the volume…");
  const [error, setError] = useState("");
  const [pdfUrl, setPdfUrl] = useState("");
  const engine = readerEngine(files, fileId);

  function persist(detail) {
    if (!work?.id || !detail) return;
    lastLoc.current = detail;
    window.clearTimeout(persistTimer.current);
    persistTimer.current = window.setTimeout(() => {
      const loc = lastLoc.current;
      if (!loc || !work?.id) return;
      const body = { position: loc.cfi || "" };
      if (typeof loc.fraction === "number") body.fraction = loc.fraction;
      api.progress(work.id, body).catch(() => {});
    }, 900);
  }

  function flushProgress() {
    window.clearTimeout(persistTimer.current);
    const loc = lastLoc.current;
    if (!loc || !work?.id) return;
    const body = { position: loc.cfi || "" };
    if (typeof loc.fraction === "number") body.fraction = loc.fraction;
    api.progress(work.id, body).catch(() => {});
  }

  function turnPage(side) {
    if (side === "left") viewRef.current?.goLeft?.();
    else if (side === "right") viewRef.current?.goRight?.();
  }

  /** Foliate has no click-to-turn; covers are SVG-only so users click and appear stuck. */
  function onPagePointer(event) {
    if (event.defaultPrevented) return;
    if (event.target?.closest?.("a[href], button, input, textarea, select, label")) return;
    const doc = event.target?.ownerDocument;
    const selection = doc?.getSelection?.();
    if (selection && !selection.isCollapsed && String(selection).trim()) return;
    const width = doc?.documentElement?.clientWidth || event.currentTarget?.clientWidth || 0;
    turnPage(pageTurnSide(event.clientX, width));
  }

  useEffect(() => {
    function onKey(event) {
      if (event.target?.closest?.("input, textarea, select, [contenteditable=true]")) return;
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onClose();
        return;
      }
      if (event.key === "/" && !event.metaKey && !event.ctrlKey && !event.altKey) {
        event.preventDefault();
        event.stopPropagation();
        return;
      }
      if (event.key === "ArrowLeft" || event.key === "PageUp") {
        event.preventDefault();
        turnPage("left");
      }
      if (event.key === "ArrowRight" || event.key === "PageDown" || event.key === " ") {
        event.preventDefault();
        turnPage("right");
      }
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [onClose]);

  useEffect(() => {
    let cancelled = false;
    let objectUrl = "";
    let view;

    async function open() {
      setError("");
      setStatus("Opening the volume…");
      if (!engine) {
        throw Object.assign(new Error("This file isn’t a readable EPUB, CBZ, or PDF."), { status: 422 });
      }
      const response = await fetch(workDownloadUrl(work.id, { inline: true, fileId }), {
        credentials: "include",
      });
      if (!response.ok) {
        const detail = await response.text().catch(() => "");
        let message = "This volume could not be opened in the reading room.";
        try {
          const parsed = JSON.parse(detail);
          if (parsed?.detail) message = String(parsed.detail);
        } catch {
          /* ignore non-JSON bodies */
        }
        throw Object.assign(new Error(message), { status: response.status });
      }
      const blob = await response.blob();
      if (cancelled) return;
      const filename = readingFileName(files, response.headers.get("content-disposition"), fileId);
      const ext = filename.includes(".") ? `.${filename.split(".").pop().toLowerCase()}` : "";
      if (ext && ![".epub", ".cbz", ".pdf"].includes(ext)) {
        throw Object.assign(new Error("This file isn’t a readable EPUB, CBZ, or PDF."), { status: 422 });
      }
      if (engine === "pdf") {
        objectUrl = URL.createObjectURL(blob);
        setPdfUrl(objectUrl);
        setStatus("");
        return;
      }
      if (engine !== "epub" && engine !== "cbz") {
        throw Object.assign(new Error("This volume isn’t a readable EPUB, CBZ, or PDF."), { status: 422 });
      }
      await import("foliate-js/view.js");
      if (cancelled || !stage.current) return;
      view = document.createElement("foliate-view");
      view.style.display = "block";
      view.style.width = "100%";
      view.style.height = "100%";
      stage.current.replaceChildren(view);
      viewRef.current = view;
      const file = new File([blob], filename, { type: blob.type || "" });
      await view.open(file);
      // Light page surface before first section paint (stored even if no doc yet).
      if (engine === "epub") view.renderer?.setStyles?.(EPUB_READER_STYLES);
      view.addEventListener("relocate", (event) => persist(event.detail));
      // Click zones live in each section document (iframe); host clicks never see them.
      view.addEventListener("load", ({ detail }) => {
        detail?.doc?.addEventListener("click", onPagePointer);
      });
      const lastLocation = progress?.position || "";
      await view.init(lastLocation ? { lastLocation } : {});
      if (!cancelled) setStatus("");
    }

    open().catch((err) => {
      if (cancelled) return;
      setStatus("");
      setError(readerOpenError(err, err?.status) || humanError(err) || "This volume could not be opened in the reading room.");
    });

    return () => {
      cancelled = true;
      flushProgress();
      viewRef.current = null;
      try {
        view?.close?.();
      } catch {
        /* view may already be gone */
      }
      view?.remove?.();
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [work.id, engine, fileId]);

  return (
    <div className="reader" role="dialog" aria-modal="true" aria-labelledby="reader-title" data-testid="reader">
      <header className="reader-head">
        <div className="reader-titleblock">
          <p className="kicker">Reading room</p>
          <h1 id="reader-title">{work.title}</h1>
        </div>
        <p className="muted reader-esc">Click edges or ← → · Esc closes</p>
        <button type="button" className="cta ghost compact" onClick={onClose} data-testid="reader-close">
          Close
        </button>
      </header>
      <div className="reader-stage" data-engine={engine || undefined}>
        {pdfUrl ? <iframe title={work.title} src={pdfUrl} /> : <div className="reader-host" ref={stage} />}
        {status ? <p className="lede reader-status">{status}</p> : null}
        {error ? <p className="alert reader-status">{error}</p> : null}
      </div>
    </div>
  );
}
