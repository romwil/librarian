/**
 * Shared job progress panel — Review Clear/Purge meters + Maintain dock cards.
 */
export default function JobProgress({
  kicker,
  testId,
  className = "ingest-progress",
  phaseLabel = "",
  done = 0,
  total = 0,
  percent = null,
  indeterminate = false,
  title = "",
  path = "",
  pathTitle = "",
  stats = [],
  tallies = [],
  statusLine = "",
  meterLabel = "Job progress",
  children = null,
}) {
  const countBit = total
    ? ` · ${done || 0} of ${total}`
    : done
      ? ` · ${done} done`
      : "";
  const percentBit = percent != null ? ` · ${percent}%` : "";
  const statsBit = stats.filter(Boolean).map((bit) => ` · ${bit}`).join("");

  return (
    <section className={className} data-testid={testId} aria-live="polite">
      {kicker ? <p className="kicker">{kicker}</p> : null}
      <p className="muted">
        {phaseLabel || "working"}
        {countBit}
        {percentBit}
        {statsBit}
      </p>
      {percent != null ? (
        <div
          className="ingest-progress-meter"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={percent}
          aria-label={meterLabel}
        >
          <span className="ingest-progress-meter-fill" style={{ width: `${percent}%` }} />
        </div>
      ) : indeterminate ? (
        <div className="ingest-progress-meter ingest-progress-meter--indeterminate" aria-hidden="true">
          <span className="ingest-progress-meter-fill" />
        </div>
      ) : null}
      {title ? <p className="lede ingest-progress-title">{title}</p> : null}
      {path ? (
        <p className="muted ingest-progress-path" title={pathTitle || path}>
          {path}
        </p>
      ) : null}
      {tallies.length ? (
        <ul className="ingest-progress-tallies">
          {tallies.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      ) : null}
      {statusLine ? (
        <p className="muted" role="status">
          {statusLine}
        </p>
      ) : null}
      {children}
    </section>
  );
}
