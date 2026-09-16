import { useEffect, useRef, useState } from "react";
import { api } from "../api.js";
import { humanError } from "../copy.js";
import { readerEngine, readingFileName } from "../reader.js";

function downloadUrl(workId) {
  return `/api/works/${encodeURIComponent(workId)}/download?inline=1`;
}

export default function Reader({ work, files = [], progress = null, onClose }) {
  const stage = useRef(null);
  const viewRef = useRef(null);
  const lastLoc = useRef(null);
  const persistTimer = useRef(0);
  const [status, setStatus] = useState("Opening the volume…");
  const [error, setError] = useState("");
  const [pdfUrl, setPdfUrl] = useState("");
  const engine = readerEngine(files);

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

  useEffect(() => {
    function onKey(event) {
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
      if (event.key === "ArrowLeft") {
        event.preventDefault();
        viewRef.current?.goLeft?.();
      }
      if (event.key === "ArrowRight") {
        event.preventDefault();
        viewRef.current?.goRight?.();
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
      const response = await fetch(downloadUrl(work.id), { credentials: "include" });
      if (!response.ok) {
        throw new Error("This volume could not be opened in the reading room.");
      }
      const blob = await response.blob();
      if (cancelled) return;
      const filename = readingFileName(files, response.headers.get("content-disposition"));
      if (engine === "pdf") {
        objectUrl = URL.createObjectURL(blob);
        setPdfUrl(objectUrl);
        setStatus("");
        return;
      }
      if (engine !== "epub" && engine !== "cbz") {
        throw new Error("This volume isn’t a readable EPUB, CBZ, or PDF.");
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
      view.addEventListener("relocate", (event) => persist(event.detail));
      const lastLocation = progress?.position || "";
      await view.init(lastLocation ? { lastLocation } : {});
      if (!cancelled) setStatus("");
    }

    open().catch((err) => {
      if (cancelled) return;
      setStatus("");
      setError(humanError(err) || "This volume could not be opened in the reading room.");
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
  }, [work.id, engine]);

  return (
    <div className="reader" role="dialog" aria-modal="true" aria-labelledby="reader-title" data-testid="reader">
      <header className="reader-head">
        <div className="reader-titleblock">
          <p className="kicker">Reading room</p>
          <h1 id="reader-title">{work.title}</h1>
        </div>
        <p className="muted reader-esc">Esc returns to the work</p>
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
