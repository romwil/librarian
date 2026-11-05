import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api } from "../api.js";
import { browseHref } from "../browse.js";
import { shelfStarterNames } from "../lib/namedShelfStarters.js";

/**
 * Hall zero-state for named shelves — create in ≤2 steps (PRD-007 / UX-006).
 * Hall chips still appear only when work_count ≥ 1.
 */
export default function HallShelfEmpty({ shelves = [], onCreated }) {
  const navigate = useNavigate();
  const [busy, setBusy] = useState("");
  const [note, setNote] = useState("");
  const starters = shelfStarterNames(shelves);

  async function createNamed(name) {
    const trimmed = String(name || "").trim();
    if (!trimmed || busy) return;
    setBusy(trimmed);
    setNote("");
    try {
      const created = await api.createShelf(trimmed, { shared: true });
      const shelf = created?.shelf || null;
      onCreated?.(shelf);
      setNote("Shared with the house — add a volume from Stacks or a work page.");
      if (shelf?.id) {
        navigate(browseHref({ shelf: shelf.id }));
      }
    } catch (err) {
      setNote(err?.message || "Could not name that shelf.");
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="hall-shelf-empty" data-testid="hall-shelf-empty" aria-label="Name a shelf">
      <h2>Name a shelf</h2>
      <p className="lede">Make a shelf for a mood, person, or project — then add a volume.</p>
      {starters.length ? (
        <div className="chip-row hall-shelf-starters" role="group" aria-label="Starter shelf names">
          {starters.map((name) => (
            <button
              key={name}
              type="button"
              className="chip"
              disabled={Boolean(busy)}
              onClick={() => createNamed(name)}
              data-testid={`hall-shelf-starter-${name.toLowerCase().replace(/\s+/g, "-")}`}
            >
              {busy === name ? "Naming…" : name}
            </button>
          ))}
        </div>
      ) : null}
      <p className="muted">
        Or open{" "}
        <Link to="/browse" data-testid="hall-shelf-stacks">
          Stacks → Name a shelf
        </Link>{" "}
        for a custom name.
      </p>
      {note ? (
        <p className="muted" data-testid="hall-shelf-empty-note">
          {note}
        </p>
      ) : null}
    </section>
  );
}
