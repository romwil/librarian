import { Link } from "react-router-dom";
import { beyondGetLabel, beyondGetPhase } from "../beyondGet.js";

/** Status + one household verb for CoverCard, peek, and the work page. */
export default function CatalogVerb({
  view,
  onAdd,
  busy = false,
  error = "",
  onFollow,
  testId = "catalog-status",
}) {
  if (!view?.show) return null;

  function follow(event) {
    if (event.metaKey || event.ctrlKey) return;
    onFollow?.(event);
  }

  const queued = view.verb === "Queued";
  const phase = beyondGetPhase({ busy, queued });
  const getLabel = beyondGetLabel(phase);
  const showGet = view.verb === "Get" || view.verb === "Queued";

  return (
    <div className="catalog-status" data-testid={testId} data-status={view.status} data-verb={view.verb}>
      {view.status ? <span className="catalog-status-label">{view.status}</span> : null}
      {view.verb === "Read" && view.readHref ? (
        <Link className="availability-link" to={view.readHref} onClick={follow} data-testid="catalog-read">
          Read
        </Link>
      ) : null}
      {view.verb === "Listen" && view.listenHref ? (
        <Link className="availability-link" to={view.listenHref} onClick={follow} data-testid="catalog-listen">
          Listen
        </Link>
      ) : null}
      {showGet && (view.canAdd || queued || busy) ? (
        <button
          type="button"
          className="cta compact"
          onClick={onAdd}
          disabled={busy || queued || !view.canAdd}
          aria-busy={busy}
          data-testid="catalog-get"
        >
          {getLabel}
        </button>
      ) : null}
      {view.verb === "Want" && view.canAdd ? (
        <button
          type="button"
          className="cta compact"
          onClick={onAdd}
          disabled={busy}
          data-testid="catalog-want"
        >
          Want
        </button>
      ) : null}
      {view.verb === "Ask the house" ? (
        <span className="catalog-status-verb" data-testid="catalog-ask">
          Ask the house
        </span>
      ) : null}
      {error ? (
        <p className="catalog-status-error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}
