import { useState } from "react";
import { MORE_SHELVES_LABEL } from "../copy.js";

/** Secondary shelves and doors. Closed until the house asks — nothing is removed. */
export default function ShelfMore({ children }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="shelf-more" data-testid="shelf-more">
      <button
        type="button"
        className="shelf-more-toggle"
        aria-expanded={open}
        onClick={() => setOpen((value) => !value)}
      >
        <span aria-hidden="true">{open ? "▾" : "▸"}</span>
        {MORE_SHELVES_LABEL}
      </button>
      <div className="shelf-more-panel" hidden={!open}>
        {children}
      </div>
    </section>
  );
}
