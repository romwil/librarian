import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { clothFor, isSquareKind, jobChipLabel } from "../cover.js";

export default function WorkPeek({ work, onClose, onRequest }) {
  const panel = useRef(null);
  const closeBtn = useRef(null);
  const navigate = useNavigate();
  const [role, setRole] = useState("reader");
  const [jobStatus, setJobStatus] = useState(work?.job_status || "");

  useEffect(() => {
    setJobStatus(work?.job_status || "");
  }, [work]);

  useEffect(() => {
    if (!work) return undefined;
    api
      .me()
      .then((data) => setRole(data.user?.role || "reader"))
      .catch(() => {});
    function onKey(event) {
      if (event.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    closeBtn.current?.focus();
    return () => window.removeEventListener("keydown", onKey);
  }, [work, onClose]);

  if (!work) return null;

  const href = work.id ? `/works/${work.id}` : null;
  const kind = work.kind || "work";
  const art = work.has_cover && work.id ? `/api/works/${work.id}/cover` : work.cover || "";
  const square = isSquareKind(kind);

  async function favorite() {
    if (!work.id) return;
    await api.favorite(work.id);
  }

  async function request() {
    const send = onRequest || api.requestItem;
    const result = await send({
      title: work.title,
      guid: work.guid,
      kind: work.kind,
      download_url: work.download_url,
      author: work.author,
      isbn: work.isbn,
    });
    const status = result?.job?.status || (role === "reader" ? "asked" : "queued");
    setJobStatus(status);
  }

  return (
    <>
      <button type="button" className="scrim" aria-label="Close peek" onClick={onClose} />
      <aside className="peek" role="dialog" aria-modal="true" aria-labelledby="peek-title" data-testid="peek" ref={panel}>
        <header className="peek-head">
          <p className="kicker">{kind}</p>
          <button type="button" className="peek-close" aria-label="Close" ref={closeBtn} onClick={onClose}>
            ×
          </button>
        </header>
        <div className="peek-body">
          <div className="peek-layout">
            <div
              className={`cover${square ? " is-square" : ""}${art ? " has-art" : ""}`}
              style={{ "--cloth": work.cloth || clothFor(work.title), width: square ? 160 : 148, height: square ? 160 : 222 }}
              aria-hidden="true"
            >
              <strong>{work.title}</strong>
              <em>{work.author || kind}</em>
              {art ? <img src={art} alt="" /> : null}
            </div>
            <div>
              <h1 id="peek-title">{work.title}</h1>
              <div className="chip-row">
                {kind ? <span className="chip is-on">{kind}</span> : null}
                {work.year ? <span className="chip">{work.year}</span> : null}
                {work.author ? <span className="chip">{work.author}</span> : null}
                {work.isbn ? <span className="chip font-mono">{work.isbn}</span> : null}
              </div>
              {work.description ? <p className="blurb">{work.description}</p> : null}
              <div className="cta-row">
                {href ? (
                  <Link
                    to={href}
                    className="cta"
                    onClick={(event) => {
                      if (event.metaKey || event.ctrlKey) return;
                      onClose();
                      navigate(href);
                      event.preventDefault();
                    }}
                  >
                    Open
                  </Link>
                ) : (
                  <button type="button" className="cta" onClick={request} disabled={Boolean(jobStatus)}>
                    {jobChipLabel(jobStatus, role)}
                  </button>
                )}
                {work.id ? (
                  <button type="button" className="cta outline" onClick={favorite}>
                    Favorite
                  </button>
                ) : null}
              </div>
              {href ? (
                <p className="peek-full">
                  <Link
                    to={href}
                    onClick={(event) => {
                      if (event.metaKey || event.ctrlKey) return;
                      onClose();
                    }}
                  >
                    Open full page
                  </Link>
                  <span style={{ color: "var(--muted)" }}> · same-tab dismisses peek · ⌘-click keeps peek</span>
                </p>
              ) : null}
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
