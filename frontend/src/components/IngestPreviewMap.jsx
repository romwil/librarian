import {
  ingestPreviewIsEmpty,
  ingestPreviewPresence,
  ingestPreviewVolumes,
  volumeIsTwin,
  volumeKindLabel,
  volumeStem,
} from "../lib/ingestPreview.js";

/** Stagger index for settle-in map rows (CSS --settle-i). */
function settleStyle(index) {
  return { "--settle-i": String(index) };
}

/**
 * Quiet map before the lamp shelves a dump — stems, twins, kinds.
 * @param {{ preview?: object | null, loading?: boolean }} props
 */
export default function IngestPreviewMap({ preview, loading = false }) {
  if (loading && !preview) {
    return (
      <section
        className="ingest-preview-map ingest-preview-alive"
        data-testid="ingest-preview-map"
        aria-label="Ingest preview"
        aria-busy="true"
      >
        <span className="ingest-preview-glow" aria-hidden="true" />
        <p className="kicker">Quiet map</p>
        <h3 className="ingest-preview-title">Look first.</h3>
        <p className="ingest-preview-presence" data-testid="ingest-preview-presence">
          The lamp is still looking…
        </p>
      </section>
    );
  }

  if (!preview) return null;

  if (ingestPreviewIsEmpty(preview)) {
    return (
      <section
        className="ingest-preview-map ingest-preview-alive ingest-preview-quiet"
        data-testid="ingest-preview-map"
        aria-label="Ingest preview"
      >
        <span className="ingest-preview-glow" aria-hidden="true" />
        <p className="kicker">Quiet map</p>
        <h3 className="ingest-preview-title">Look first.</h3>
        <p className="ingest-preview-presence" data-testid="ingest-preview-presence">
          <span data-testid="ingest-preview-empty">{ingestPreviewPresence(preview)}</span>
        </p>
      </section>
    );
  }

  const volumes = ingestPreviewVolumes(preview);

  return (
    <section
      className="ingest-preview-map ingest-preview-alive"
      data-testid="ingest-preview-map"
      aria-label="Ingest preview"
    >
      <span className="ingest-preview-glow" aria-hidden="true" />
      <p className="kicker">Quiet map</p>
      <h3 className="ingest-preview-title">Look first.</h3>
      <p className="ingest-preview-presence" data-testid="ingest-preview-presence">
        {ingestPreviewPresence(preview)}
      </p>
      <ul className="ingest-preview-list">
        {volumes.map((volume, index) => {
          const twin = volumeIsTwin(volume);
          return (
            <li
              key={volume.id || volume.path || index}
              className={
                twin
                  ? "ingest-preview-row cover-settle is-twin is-breathing"
                  : "ingest-preview-row cover-settle"
              }
              style={settleStyle(index)}
              data-testid="ingest-preview-volume"
              data-role={volume.role || (twin ? "twin" : "ready")}
              data-kind={volume.kind || ""}
            >
              <p className="ingest-preview-stem">{volumeStem(volume)}</p>
              <p className="ingest-preview-meta">
                {volumeKindLabel(volume)}
                {twin ? " · twin" : ""}
              </p>
            </li>
          );
        })}
      </ul>
      {preview.truncated ? (
        <p className="muted ingest-preview-more" data-testid="ingest-preview-truncated">
          And more beyond this map — Add still shelves the whole dump.
        </p>
      ) : null}
    </section>
  );
}
