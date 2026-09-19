/** Collapsed search decision trail — Find, Bestsellers chase, re-grab. */

export default function SearchTraceDisclosure({
  conversation = [],
  steps = [],
  results = [],
  candidates = [],
  rankMethod = "",
  rankReason = "",
  summary = "",
  testId = "search-trace",
}) {
  const hasBody =
    (conversation && conversation.length) ||
    (steps && steps.length) ||
    (results && results.length) ||
    (candidates && candidates.length);
  if (!hasBody && !rankMethod && !summary) return null;

  const head =
    summary ||
    [rankMethod ? `rank ${rankMethod}` : "", rankReason, candidates?.length ? `${candidates.length} remembered` : ""]
      .filter(Boolean)
      .join(" · ");

  return (
    <details className="bestsellers-chase-trace search-trace" data-testid={testId}>
      <summary>
        Search details
        {head ? <span className="muted"> — {head}</span> : null}
      </summary>
      <div className="bestsellers-chase-trace-body">
        {conversation?.length ? (
          <section>
            <p className="kicker">Conversation</p>
            <ol className="bestsellers-chase-log">
              {conversation.map((row, index) => (
                <li key={`${row.role || "note"}-${index}`}>
                  <span className="muted">{row.role || "note"}</span> {row.content}
                </li>
              ))}
            </ol>
          </section>
        ) : null}
        {steps?.length ? (
          <section>
            <p className="kicker">Queries / steps</p>
            <ol className="bestsellers-chase-log">
              {steps.map((row, index) => (
                <li key={`${row.step || "step"}-${index}`}>
                  <span className="muted">{row.step || "step"}</span> {row.detail}
                </li>
              ))}
            </ol>
          </section>
        ) : null}
        {results?.length ? (
          <section>
            <p className="kicker">Result set</p>
            <ol className="bestsellers-chase-log" data-testid={`${testId}-results`}>
              {results.map((row, index) => (
                <li key={`${row.guid || row.title}-${index}`}>
                  <strong>{row.decision || "row"}</strong>
                  {row.reason ? ` — ${row.reason}` : ""} · {row.title || "(untitled)"}
                  {row.guid ? ` · ${row.guid}` : ""}
                  {row.kind ? ` · ${row.kind}` : ""}
                  {row.host_name || row.host ? ` · ${row.host_name || row.host}` : ""}
                </li>
              ))}
            </ol>
          </section>
        ) : null}
        {candidates?.length ? (
          <section>
            <p className="kicker">Remembered alternates</p>
            <ol className="bestsellers-chase-log" data-testid={`${testId}-candidates`}>
              {candidates.map((row, index) => (
                <li key={`${row.guid}-${index}`}>
                  {row.rank ? `#${row.rank} ` : ""}
                  {row.title || "(untitled)"}
                  {row.guid ? ` · ${row.guid}` : ""}
                  {row.note ? ` · ${row.note}` : ""}
                </li>
              ))}
            </ol>
          </section>
        ) : null}
      </div>
    </details>
  );
}
