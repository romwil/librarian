import {
  lanternPresence,
  lanternStatsModel,
  lanternWeather,
  scorecardLanterns,
  scorecardPresence,
} from "../lib/indexerScorecard.js";

function LanternStats({ row, showExtra }) {
  const model = lanternStatsModel(row, { showExtra });
  if (!model) return null;
  return (
    <div className="indexer-lantern-bi" data-testid="indexer-lantern-stats">
      <div className="indexer-kpi-row">
        <p className="indexer-kpi-rate">{model.percent}</p>
        <p className="indexer-kpi-meta">
          match · {model.spokenLabel}
        </p>
      </div>
      {model.kinds.length > 0 ? (
        <ul className="indexer-kind-bars">
          {model.kinds.map((kind) => (
            <li
                key={kind.kind || "any"}
                className="indexer-kind-bar"
                aria-label={`${kind.label} ${kind.percent} match`}
              >
              <span className="indexer-kind-label">{kind.label}</span>
              <span
                className="indexer-kind-track"
                aria-hidden="true"
              >
                <span
                  className="indexer-kind-fill"
                  style={{ width: `${kind.fill}%` }}
                />
              </span>
              <span className="indexer-kind-pct">{kind.percent}</span>
            </li>
          ))}
        </ul>
      ) : null}
      {model.notes ? <p className="indexer-kpi-notes">{model.notes}</p> : null}
    </div>
  );
}

/**
 * Maintain indexer lanterns — mute a sick host without deleting it.
 * Compact BI chips show match rate by media type when Finds have spoken.
 * @param {{
 *   card?: object | null,
 *   loading?: boolean,
 *   busyId?: string,
 *   onMute?: (hostId: string) => void,
 *   onUnmute?: (hostId: string) => void,
 * }} props
 */
export default function IndexerScorecard({
  card = null,
  loading = false,
  busyId = "",
  onMute,
  onUnmute,
}) {
  if (loading && !card) {
    return (
      <section
        className="indexer-scorecard indexer-scorecard-quiet"
        data-testid="indexer-scorecard"
        aria-label="Indexer lanterns"
        aria-busy="true"
      >
        <span className="indexer-scorecard-glow" aria-hidden="true" />
        <p className="kicker">Find lanterns</p>
        <h2 className="indexer-scorecard-title">Indexer scorecard</h2>
        <p className="indexer-scorecard-presence" data-testid="indexer-scorecard-presence">
          Warming the lanterns…
        </p>
      </section>
    );
  }

  if (!card) return null;

  const lanterns = scorecardLanterns(card);
  const showExtra = Boolean(card.show_extra_categories);

  return (
    <section
      className="indexer-scorecard"
      data-testid="indexer-scorecard"
      aria-label="Indexer lanterns"
    >
      <span className="indexer-scorecard-glow" aria-hidden="true" />
      <p className="kicker">Find lanterns</p>
      <h2 className="indexer-scorecard-title">Indexer scorecard</h2>
      <p className="indexer-scorecard-presence" data-testid="indexer-scorecard-presence">
        {scorecardPresence(card)}
      </p>
      {lanterns.length === 0 ? (
        <p className="muted" data-testid="indexer-scorecard-empty">
          Add an indexer in Settings — lanterns light when Find speaks.
        </p>
      ) : (
        <ul className="indexer-lantern-list">
          {lanterns.map((row, index) => {
            const weather = lanternWeather(row);
            const muted = Boolean(row.muted) || weather === "muted";
            const busy = String(busyId) === String(row.id);
            return (
              <li
                key={row.id || index}
                className={`indexer-lantern indexer-lantern-${weather}${muted ? " is-muted" : ""}`}
                data-testid="indexer-lantern"
                data-weather={weather}
                style={{ "--settle-i": String(index) }}
              >
                <span className="indexer-lantern-flame" aria-hidden="true" />
                <div className="indexer-lantern-copy">
                  <p className="indexer-lantern-name">{row.name || "Indexer"}</p>
                  <p className="indexer-lantern-presence">{lanternPresence(row)}</p>
                  <LanternStats row={row} showExtra={showExtra} />
                </div>
                {row.can_mute ? (
                  <div className="indexer-lantern-actions">
                    {muted ? (
                      <button
                        type="button"
                        className="cta outline compact"
                        disabled={busy || !onUnmute}
                        aria-busy={busy || undefined}
                        onClick={() => onUnmute?.(row.id)}
                        data-testid="indexer-lantern-unmute"
                      >
                        {busy ? "…" : "Unmute"}
                      </button>
                    ) : (
                      <button
                        type="button"
                        className="cta ghost compact"
                        disabled={busy || !onMute}
                        aria-busy={busy || undefined}
                        onClick={() => onMute?.(row.id)}
                        data-testid="indexer-lantern-mute"
                      >
                        {busy ? "…" : "Mute"}
                      </button>
                    )}
                  </div>
                ) : null}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
