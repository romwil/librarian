import { useState } from "react";
import { api } from "../api.js";
import { shelfStarterNames } from "../lib/namedShelfStarters.js";

/**
 * Name a household shelf. The Stacks command bar keeps this form behind
 * one control so the shelf count and covers stay at the top of the results.
 * Starter chips keep zero-state activation ≤2 steps (PRD-007 / UX-006).
 */
export default function NamedShelves({ presence = "", shelves = [], onChanged }) {
  const [name, setName] = useState("");
  const [shared, setShared] = useState(true);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState("");
  const starters = shelfStarterNames(shelves);

  async function createNamed(trimmed, { shared: shareFlag } = { shared }) {
    if (!trimmed || busy) return;
    setBusy(true);
    setNote("");
    try {
      const created = await api.createShelf(trimmed, { shared: shareFlag });
      setName("");
      setNote(shareFlag ? "Shared with the house." : "A quiet corner of your own.");
      onChanged?.(created?.shelf || null);
    } catch (err) {
      setNote(err?.message || "Could not name that shelf.");
    } finally {
      setBusy(false);
    }
  }

  async function createShelf(event) {
    event.preventDefault();
    await createNamed(String(name || "").trim(), { shared });
  }

  return (
    <section className="named-shelves" data-testid="named-shelves" aria-label="Named shelves">
      <p className="named-shelves-presence" data-testid="named-shelves-presence">
        {presence || "Name a shelf for the house — Beach, Kids comics, whatever fits."}
      </p>

      {starters.length ? (
        <div className="chip-row named-shelves-starters" role="group" aria-label="Starter shelf names">
          {starters.map((starter) => (
            <button
              key={starter}
              type="button"
              className="chip"
              disabled={busy}
              onClick={() => createNamed(starter, { shared: true })}
              data-testid={`named-shelves-starter-${starter.toLowerCase().replace(/\s+/g, "-")}`}
            >
              {starter}
            </button>
          ))}
        </div>
      ) : null}

      <form className="named-shelves-form" onSubmit={createShelf}>
        <label className="named-shelves-label">
          <span className="sr-only">Shelf name</span>
          <input
            type="text"
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Beach, Kids comics…"
            maxLength={48}
            aria-label="Shelf name"
            data-testid="named-shelves-name"
          />
        </label>
        <label className="named-shelves-share">
          <input
            type="checkbox"
            checked={shared}
            onChange={(event) => setShared(event.target.checked)}
            data-testid="named-shelves-shared"
          />
          <span>Share with the house</span>
        </label>
        <button
          type="submit"
          className="cta compact"
          disabled={busy || !String(name || "").trim()}
          data-testid="named-shelves-create"
        >
          {busy ? "Naming…" : "Name this shelf"}
        </button>
      </form>
      {note ? (
        <p className="muted" data-testid="named-shelves-note">
          {note}
        </p>
      ) : null}
    </section>
  );
}
