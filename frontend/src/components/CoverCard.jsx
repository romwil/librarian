import { useWorkPeek } from "./WorkPeekProvider.jsx";

function shouldOpenPeek(event) {
  return !(event.metaKey || event.ctrlKey || event.shiftKey || event.altKey);
}

export default function CoverCard({ work, href, onRequest, badge }) {
  const peek = useWorkPeek();
  const kind = work.kind || work.category || "book";
  const square = kind === "music" || kind === "audiobook";
  const title = work.title || "Untitled";

  function onClick(event) {
    if (work.id && shouldOpenPeek(event)) {
      event.preventDefault();
      peek.openWork(work, { triggerEl: event.currentTarget });
    }
  }

  return (
    <article className={`cover-card ${square ? "cover-card--square" : ""}`}>
      <a href={href || (work.id ? `/works/${work.id}` : "#")} className="cover-poster" onClick={onClick}>
        <span className="cover-cloth">{title.slice(0, 1)}</span>
        {badge ? <span className="cover-badge">{badge}</span> : null}
      </a>
      <p className="cover-title">{title}</p>
      <p className="cover-meta">{work.author || work.series_name || kind}</p>
      {onRequest && !work.id ? (
        <button type="button" className="chip" onClick={() => onRequest(work)}>
          Request
        </button>
      ) : null}
    </article>
  );
}
