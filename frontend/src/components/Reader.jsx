import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { humanError } from "../copy.js";
import {
  EPUB_READER_STYLES,
  comicSpreadMode,
  comicTurnSide,
  pageTurnTarget,
  readerChromeHint,
  readerEngine,
  readerFlow,
  readerOpenError,
  readerWheelDelta,
  readingFileName,
  scrollReader,
  turnReaderPage,
  workDownloadUrl,
} from "../reader.js";
import {
  READER_CHROME_IDLE_MS,
  prefersReducedMotion,
  readerCalmClassNames,
} from "../lib/readingRoomCalm.js";

export default function Reader({ work, files = [], fileId = "", progress = null, onClose }) {
  const stage = useRef(null);
  const viewRef = useRef(null);
  const imageFrame = useRef(null);
  const turnedByPointer = useRef(0);
  const lastLoc = useRef(null);
  const persistTimer = useRef(0);
  const [status, setStatus] = useState("Opening the volume…");
  const [error, setError] = useState("");
  const [pdfUrl, setPdfUrl] = useState("");
  const [chromeDim, setChromeDim] = useState(false);
  const reducedMotion = prefersReducedMotion();
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
    turnReaderPage(viewRef.current, side);
  }

  /** Foliate has no click-to-turn. Section clicks only see the page image. */
  function onPagePointer(event) {
    if (event.defaultPrevented) return;
    if (event.target?.closest?.("a[href], button, input, textarea, select, label")) return;
    const doc = event.target?.ownerDocument;
    const selection = doc?.getSelection?.();
    if (selection && !selection.isCollapsed && String(selection).trim()) return;
    const frame = doc?.defaultView?.frameElement;
    if (frame) imageFrame.current = frame;
    const rect = doc?.documentElement?.getBoundingClientRect?.();
    const width = rect?.width || doc?.documentElement?.clientWidth || event.currentTarget?.clientWidth || 0;
    turnPage(pageTurnTarget(event.clientX, { left: rect?.left || 0, width }));
  }

  function comicSide(event) {
    const explicit = event.target?.closest?.("[data-turn]")?.getAttribute?.("data-turn");
    if (explicit === "left" || explicit === "right") return explicit;
    const stageBox = event.currentTarget?.getBoundingClientRect?.();
    const imageBox = imageFrame.current?.getBoundingClientRect?.();
    return comicTurnSide(event.clientX, stageBox, imageBox);
  }

  /**
   * CBZ letterbox lives on the host stage, outside the page iframe.
   * Those taps never reach the section document, so the stage itself turns.
   */
  function onComicPointerUp(event) {
    if (engine !== "cbz") return;
    if (event.button != null && event.button !== 0) return;
    if (event.target?.closest?.("a[href], input, textarea, select, label")) return;
    const side = comicSide(event);
    if (!side) return;
    const gesture = turnedByPointer.current + 1;
    turnedByPointer.current = gesture;
    window.setTimeout(() => {
      if (turnedByPointer.current === gesture) turnedByPointer.current = 0;
    }, 400);
    turnPage(side);
  }

  function onComicClick(event) {
    if (engine !== "cbz") return;
    if (turnedByPointer.current) {
      turnedByPointer.current = 0;
      return;
    }
    if (event.target?.closest?.("a[href], input, textarea, select, label")) return;
    turnPage(comicSide(event));
  }


  useEffect(() => {
    if (reducedMotion) {
      setChromeDim(false);
      return undefined;
    }
    let timer = window.setTimeout(() => setChromeDim(true), READER_CHROME_IDLE_MS);
    function wake() {
      setChromeDim(false);
      window.clearTimeout(timer);
      timer = window.setTimeout(() => setChromeDim(true), READER_CHROME_IDLE_MS);
    }
    window.addEventListener("pointermove", wake, { passive: true });
    window.addEventListener("keydown", wake, true);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("pointermove", wake);
      window.removeEventListener("keydown", wake, true);
    };
  }, [reducedMotion]);

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
      if (engine === "cbz") {
        comicSpreadMode(view.book);
        view.renderer?.open?.(view.book);
      }
      const flow = readerFlow(engine, view.isFixedLayout);
      if (flow) view.renderer?.setAttribute("flow", flow);
      view.addEventListener("relocate", (event) => persist(event.detail));
      const touch = { x: 0, y: 0, active: false };
      function onReaderWheel(event) {
        const renderer = view.renderer;
        if (!renderer || renderer.getAttribute("flow") !== "scrolled") return;
        const delta = readerWheelDelta(event);
        if (!delta) return;
        event.preventDefault();
        scrollReader(renderer, delta);
      }
      function onTouchStart(event) {
        const point = event.touches?.[0];
        if (!point || event.touches.length !== 1) {
          touch.active = false;
          return;
        }
        touch.x = point.screenX;
        touch.y = point.screenY;
        touch.active = true;
      }
      function onTouchMove(event) {
        const renderer = view.renderer;
        if (!touch.active || !renderer || renderer.getAttribute("flow") !== "scrolled") return;
        const point = event.touches?.[0];
        if (!point || event.touches.length !== 1) return;
        const selection = event.target?.ownerDocument?.getSelection?.();
        if (selection && !selection.isCollapsed && String(selection).trim()) return;
        const dx = touch.x - point.screenX;
        const dy = touch.y - point.screenY;
        touch.x = point.screenX;
        touch.y = point.screenY;
        const delta = Math.abs(dy) >= Math.abs(dx) ? dy : dx;
        if (!delta) return;
        event.preventDefault();
        scrollReader(renderer, delta);
      }
      // Click and scroll zones live in each section document (iframe); host events never see them.
      view.addEventListener("load", ({ detail }) => {
        const doc = detail?.doc;
        if (!doc) return;
        const frame = doc.defaultView?.frameElement;
        if (frame) imageFrame.current = frame;
        doc.addEventListener("click", onPagePointer);
        if (view.renderer?.getAttribute("flow") !== "scrolled") return;
        doc.addEventListener("wheel", onReaderWheel, { passive: false });
        doc.addEventListener("touchstart", onTouchStart, { passive: true });
        doc.addEventListener("touchmove", onTouchMove, { passive: false });
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
    <div
      className={readerCalmClassNames({ chromeDim, reducedMotion })}
      role="dialog"
      aria-modal="true"
      aria-labelledby="reader-title"
      data-testid="reader"
      data-calm="true"
    >
      <header className="reader-head" data-testid="reader-head">
        <div className="reader-titleblock">
          <p className="kicker">Reading room</p>
          <h1 id="reader-title">{work.title}</h1>
        </div>
        <p className="muted reader-esc">{readerChromeHint(engine)}</p>
        <button type="button" className="cta ghost compact" onClick={onClose} data-testid="reader-close">
          Close
        </button>
      </header>
      <div
        className="reader-stage"
        data-engine={engine || undefined}
        data-testid="reader-stage"
        onPointerUp={engine === "cbz" ? onComicPointerUp : undefined}
        onClick={engine === "cbz" ? onComicClick : undefined}
      >
        {pdfUrl ? <iframe title={work.title} src={pdfUrl} /> : <div className="reader-host" ref={stage} />}
        {engine === "cbz" ? (
          <div className="reader-turns">
            <button type="button" className="reader-turn is-left" data-turn="left" aria-label="Previous page" />
            <button type="button" className="reader-turn is-right" data-turn="right" aria-label="Next page" />
          </div>
        ) : null}
        {status ? <p className="lede reader-status">{status}</p> : null}
        {error ? <p className="alert reader-status">{error}</p> : null}
      </div>
    </div>
  );
}
