import { useState } from "react";
import {
  renormalizeIsAvailable,
  renormalizePresence,
  renormalizeReadyCount,
} from "../lib/calibreRenormalize.js";

/**
 * One-button Calibre re-normalize — look first, then shelve as copy.
 */
export default function CalibreRenormalize({ preview, loading = false, busy = false, onLook, onApply }) {
  const [confirming, setConfirming] = useState(false);
  const available = renormalizeIsAvailable(preview);
  const ready = renormalizeReadyCount(preview);

  return (
    <section
      className={`calibre-renormalize calibre-renormalize-alive${available ? "" : " is-quiet"}`}
      data-testid="calibre-renormalize"
      aria-label="Calibre re-normalize"
      aria-busy={loading || busy || undefined}
    >
      <span className="calibre-renormalize-glow" aria-hidden="true" />
      <p className="kicker">Calibre dump</p>
      <h3 className="calibre-renormalize-title">Re-normalize</h3>
      <p className="calibre-renormalize-presence" data-testid="calibre-renormalize-presence">
        {loading ? "The lamp is looking…" : renormalizePresence(preview)}
      </p>
      <div className="calibre-renormalize-actions cta-row">
        <button
          type="button"
          className="cta outline compact"
          onClick={onLook}
          disabled={loading || busy}
          data-testid="calibre-renormalize-look"
        >
          {loading ? "Looking…" : "Look first"}
        </button>
        {available && ready > 0 ? (
          confirming ? (
            <button
              type="button"
              className="cta compact"
              onClick={() => {
                setConfirming(false);
                onApply?.();
              }}
              disabled={busy}
              data-testid="calibre-renormalize-apply"
            >
              {busy ? "Shelving…" : `Shelve ${ready}`}
            </button>
          ) : (
            <button
              type="button"
              className="cta outline compact"
              onClick={() => setConfirming(true)}
              disabled={busy}
              data-testid="calibre-renormalize-confirm"
            >
              Ready to shelve
            </button>
          )
        ) : null}
      </div>
    </section>
  );
}
