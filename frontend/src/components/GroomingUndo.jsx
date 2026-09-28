import { undoIsAvailable, undoLabel, undoPresence } from "../lib/groomingUndo.js";

/**
 * Safe undo for the last Clear/Purge/Skip batch.
 * @param {{
 *   undo?: object | null,
 *   loading?: boolean,
 *   busy?: boolean,
 *   onUndo?: () => void,
 * }} props
 */
export default function GroomingUndo({ undo = null, loading = false, busy = false, onUndo }) {
  if (loading && !undo) {
    return (
      <section
        className="grooming-undo grooming-undo-quiet"
        data-testid="grooming-undo"
        aria-label="Safe undo"
        aria-busy="true"
      >
        <p className="kicker">Safe undo</p>
        <p className="grooming-undo-presence" data-testid="grooming-undo-presence">
          Checking the last tend…
        </p>
      </section>
    );
  }

  if (!undo) return null;

  const available = undoIsAvailable(undo);

  return (
    <section
      className={`grooming-undo${available ? " is-available" : " grooming-undo-quiet"}`}
      data-testid="grooming-undo"
      aria-label="Safe undo"
    >
      <p className="kicker">Safe undo</p>
      <p className="grooming-undo-presence" data-testid="grooming-undo-presence">
        {undoPresence(undo)}
      </p>
      {available ? (
        <p className="grooming-undo-actions">
          <button
            type="button"
            className="cta outline compact"
            disabled={busy || !onUndo}
            aria-busy={busy || undefined}
            onClick={() => onUndo?.()}
            data-testid="grooming-undo-restore"
          >
            {busy ? "Restoring…" : `Undo ${undoLabel(undo)}`}
          </button>
        </p>
      ) : null}
    </section>
  );
}
