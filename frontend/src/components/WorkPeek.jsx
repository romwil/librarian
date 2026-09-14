import { useEffect, useRef } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api.js";

export default function WorkPeek({ work, onClose }) {
  const panel = useRef(null);
  const navigate = useNavigate();

  useEffect(() => {
    if (!work) return undefined;
    function onKey(event) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    panel.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [work, onClose]);

  if (!work) return null;

  const href = work.id ? `/works/${work.id}` : null;

  async function favorite() {
    if (!work.id) return;
    await api.favorite(work.id);
  }

  async function request() {
    await api.requestItem({
      title: work.title,
      guid: work.guid,
      kind: work.kind,
      download_url: work.download_url,
      author: work.author,
      isbn: work.isbn,
    });
    onClose();
  }

  return (
    <div className="peek-scrim" onClick={onClose} role="presentation">
      <div
        className="peek-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="peek-title"
        ref={panel}
        tabIndex={-1}
        onClick={(event) => event.stopPropagation()}
      >
        <p className="eyebrow">{work.kind || "work"}</p>
        <h2 id="peek-title">{work.title}</h2>
        <p className="muted">{[work.author, work.series_name, work.series_index].filter(Boolean).join(" · ")}</p>
        {work.description ? <p className="peek-blurb">{work.description}</p> : null}
        <div className="peek-acts">
          {href ? (
            <Link
              to={href}
              className="primary"
              onClick={(event) => {
                if (event.metaKey || event.ctrlKey) return;
                onClose();
                navigate(href);
                event.preventDefault();
              }}
            >
              Open full page
            </Link>
          ) : (
            <button type="button" className="primary" onClick={request}>
              Request
            </button>
          )}
          {work.id ? (
            <button type="button" className="ghost" onClick={favorite}>
              Favorite
            </button>
          ) : null}
          <button type="button" className="ghost" onClick={onClose}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}
