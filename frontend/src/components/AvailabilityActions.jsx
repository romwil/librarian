import { Link } from "react-router-dom";

/**
 * Verb cluster for a shelved book.
 * Cards include Read and Download. Peek and the work page already have those,
 * so they pass shelfVerbs={false} and keep Listen or Wanted.
 */
export default function AvailabilityActions({
  view,
  shelfVerbs = false,
  onAdd,
  onDismiss,
  busy = false,
  onFollow,
  testId = "availability",
}) {
  if (!view?.show) return null;
  const cta = !shelfVerbs;

  function follow(event) {
    if (event.metaKey || event.ctrlKey) return;
    onFollow?.(event);
  }

  return (
    <div className={`availability${cta ? " is-cta" : ""}`} data-testid={testId} data-verb={view.verb}>
      {view.verb === "want" ? (
        <p className="availability-note" data-testid="availability-wanted">
          <span className="availability-verb">Wanted</span>
          {view.note ? <span className="availability-aside">{view.note}</span> : null}
        </p>
      ) : null}
      <div className="availability-links">
        {view.verb === "listen" && view.listenHref ? (
          <Link className={cta ? "cta compact" : "availability-link"} to={view.listenHref} onClick={follow} data-testid="availability-listen">
            Listen
          </Link>
        ) : null}
        {shelfVerbs && view.readHref ? (
          <Link className="availability-link" to={view.readHref} onClick={follow} data-testid="availability-read">
            Read
          </Link>
        ) : null}
        {shelfVerbs && view.downloadHref ? (
          <a className="availability-link" href={view.downloadHref} data-testid="availability-download">
            Download
          </a>
        ) : null}
        {view.verb === "want" && view.searchHref ? (
          <Link className={cta ? "cta outline compact" : "availability-link"} to={view.searchHref} onClick={follow} data-testid="availability-search">
            Search the shelves
          </Link>
        ) : null}
        {view.verb === "want" && view.findHref ? (
          <Link className={cta ? "cta outline compact" : "availability-link"} to={view.findHref} onClick={follow} data-testid="availability-find">
            Find beyond
          </Link>
        ) : null}
        {view.canAdd ? (
          <button type="button" className={cta ? "cta outline compact" : "availability-link"} onClick={onAdd} disabled={busy} data-testid="availability-add">
            Add to Wanted
          </button>
        ) : null}
        {view.canDismiss ? (
          <button type="button" className={cta ? "cta outline compact" : "availability-link"} onClick={onDismiss} disabled={busy} data-testid="availability-dismiss">
            Dismiss
          </button>
        ) : null}
      </div>
    </div>
  );
}
