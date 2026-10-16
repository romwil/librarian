/** One field, one mode. Title, author, ISBN, series, or narrator. */

export const SEARCH_MODES = [
  ["title", "Title"],
  ["author", "Author"],
  ["isbn", "ISBN"],
  ["series", "Series"],
  ["narrator", "Narrator"],
];

export function normalizeSearchMode(value) {
  const key = String(value || "").trim().toLowerCase();
  return SEARCH_MODES.some(([mode]) => mode === key) ? key : "";
}

export default function SearchModeControl({ mode = "title", onMode }) {
  const active = normalizeSearchMode(mode) || "title";
  return (
    <div className="search-hero chip-row" role="radiogroup" aria-label="Search mode" data-testid="search-mode">
      {SEARCH_MODES.map(([value, label]) => (
        <button
          key={value}
          type="button"
          role="radio"
          className={`chip${active === value ? " is-on" : ""}`}
          aria-checked={active === value}
          data-testid={`search-mode-${value}`}
          onClick={() => onMode?.(value)}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
