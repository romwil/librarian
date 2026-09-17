export default function PlexampToast({ handoff, onClose }) {
  if (!handoff || handoff.kind === "audiobook") return null;
  const art = handoff.has_cover && handoff.work_id ? `/api/works/${handoff.work_id}/cover` : "";

  return (
    <aside className="plexamp-toast" data-testid="plexamp-toast" role="status">
      {art ? <img src={art} alt="" className="plexamp-toast-art" /> : <span className="plexamp-toast-cloth" aria-hidden="true" />}
      <div className="plexamp-toast-copy">
        <p className="kicker">Plexamp</p>
        <strong>{handoff.title}</strong>
        {handoff.artist ? <p className="muted">{handoff.artist}</p> : null}
        <p className="muted">{handoff.message || "On the music shelf for Plexamp"}</p>
        <div className="cta-row compact">
          <a className="cta compact" href={handoff.href || "plexamp://"}>
            Open Plexamp
          </a>
          <button type="button" className="cta ghost compact" onClick={onClose}>
            Dismiss
          </button>
        </div>
      </div>
    </aside>
  );
}
