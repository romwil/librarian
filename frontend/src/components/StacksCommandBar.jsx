import { useEffect, useState } from "react";
import NamedShelves from "./NamedShelves.jsx";
import { useAnchoredPopover } from "../hooks/useAnchoredPopover.js";
import {
  BROWSE_EXPORT_COLUMNS,
  BROWSE_PAGE_SIZES,
  BROWSE_SORT_OPTIONS,
  browseExportHref,
  browseKinds,
  browseHasActiveFilters,
  sortChangePatch,
  sortDirLabel,
} from "../browse.js";

const PHONE_FILTERS = "(max-width: 720px)";

/** Phone collapses the filters. Desktop keeps the same disclosure open so the bar is in the tab order. */
function useStacksFiltersOpen() {
  const [phone, setPhone] = useState(() =>
    typeof window !== "undefined" ? window.matchMedia(PHONE_FILTERS).matches : false,
  );
  const [phoneOpen, setPhoneOpen] = useState(false);

  useEffect(() => {
    const media = window.matchMedia(PHONE_FILTERS);
    const onChange = () => setPhone(media.matches);
    onChange();
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, []);

  return {
    open: phone ? phoneOpen : true,
    onToggle(event) {
      if (!window.matchMedia(PHONE_FILTERS).matches) {
        event.currentTarget.open = true;
        return;
      }
      setPhoneOpen(event.currentTarget.open);
    },
  };
}

/** One popover style shared by the grip menu, filter menus, columns, and export. */
function FacetMenu({ label, activeLabel, children, testId }) {
  const { open, setOpen, rootRef, popoverRef } = useAnchoredPopover({ closeOnEscape: true });
  return (
    <div className="stacks-menu-wrap" ref={rootRef} data-testid={testId}>
      <button type="button" className="stacks-menu-trigger" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        {label}
        {activeLabel ? <span className="stacks-menu-active muted"> · {activeLabel}</span> : null}
      </button>
      {open ? (
        <div className="work-action-popover is-static" role="menu" ref={popoverRef}>
          {children}
        </div>
      ) : null}
    </div>
  );
}

/** Author / Series / Genre — single-select facet list fed by `/api/browse/facets`. */
function SingleSelectFacetMenu({ label, rows, value, onChange, testId }) {
  const list = Array.isArray(rows) ? rows : [];
  if (!list.length && !value) return null;
  return (
    <FacetMenu label={label} activeLabel={value || ""} testId={testId}>
      <button type="button" className="work-action-item" onClick={() => onChange("")}>
        Any {label.toLowerCase()}
      </button>
      {list.map((row) => (
        <button
          key={row.name}
          type="button"
          className="work-action-item"
          onClick={() => onChange(value.toLowerCase() === row.name.toLowerCase() ? "" : row.name)}
        >
          {value.toLowerCase() === row.name.toLowerCase() ? "✓ " : ""}
          {row.name}
          {row.count != null ? <span className="muted"> {row.count}</span> : null}
        </button>
      ))}
    </FacetMenu>
  );
}

function ColumnsMenu({ columns, onToggle }) {
  return (
    <FacetMenu label="Columns" testId="stacks-columns-menu">
      {BROWSE_EXPORT_COLUMNS.map((col) => (
        <label key={col} className="work-action-item work-action-check">
          <input type="checkbox" checked={columns.includes(col)} onChange={() => onToggle(col)} />
          {col}
        </label>
      ))}
    </FacetMenu>
  );
}

function ExportMenu({ filters, columns }) {
  return (
    <FacetMenu label="Export CSV" testId="stacks-export-menu">
      <a className="work-action-item" href={browseExportHref(filters, { columns })} data-testid="stacks-export-visible">
        Visible columns
      </a>
      <a
        className="work-action-item"
        href={browseExportHref(filters, { columns: BROWSE_EXPORT_COLUMNS })}
        data-testid="stacks-export-all"
      >
        All columns
      </a>
    </FacetMenu>
  );
}

export default function StacksCommandBar({
  filters,
  facets,
  onPatchFilters,
  view,
  onViewChange,
  listColumns,
  onToggleColumn,
  pageSize,
  onPageSizeChange,
  authorRows,
  seriesRows,
  genreRows,
  showGenres,
  shelves = [],
  shelfPresence = "",
  onShelfNamed,
}) {
  const activeCount = [
    filters.kind,
    filters.author,
    filters.letter,
    filters.series,
    filters.genre,
    filters.shelf,
  ].filter(Boolean).length;
  const filtersOpen = useStacksFiltersOpen();

  return (
    <div className="stacks-bar" data-testid="stacks-bar">
      <details className="stacks-filters" open={filtersOpen.open} onToggle={filtersOpen.onToggle}>
        <summary className="stacks-filters-toggle" role="button" data-testid="stacks-filters-toggle">
          Filters{activeCount ? ` (${activeCount})` : ""}
        </summary>
        <div className="stacks-filters-body">
          <label className="field-inline">
            <span>Kind</span>
            <select
              value={filters.kind || ""}
              data-testid="stacks-kind"
              onChange={(event) => onPatchFilters({ kind: event.target.value })}
            >
              <option value="">All kinds</option>
              {browseKinds().map((kind) => (
                <option key={kind} value={kind}>
                  {kind}
                </option>
              ))}
            </select>
          </label>
          <label className="field-inline">
            <span>Shelf</span>
            <select
              value={filters.shelf || ""}
              data-testid="stacks-shelf"
              onChange={(event) => onPatchFilters({ shelf: event.target.value })}
            >
              <option value="">Any shelf</option>
              <option value="favorites">Favorites</option>
              {shelves
                .filter((shelf) => shelf?.id && shelf?.name)
                .map((shelf) => (
                  <option key={shelf.id} value={shelf.id}>
                    {shelf.name}
                  </option>
                ))}
            </select>
          </label>
          <label className="field-inline">
            <span>Letter</span>
            <select
              value={filters.letter || ""}
              data-testid="stacks-letter"
              onChange={(event) => onPatchFilters({ letter: event.target.value })}
            >
              <option value="">Any letter</option>
              <option value="#">#</option>
              {"ABCDEFGHIJKLMNOPQRSTUVWXYZ".split("").map((letter) => (
                <option key={letter} value={letter}>
                  {letter}
                </option>
              ))}
            </select>
          </label>
          <SingleSelectFacetMenu
            label="Author"
            rows={authorRows}
            value={filters.author || ""}
            onChange={(author) => onPatchFilters({ author })}
            testId="stacks-author-menu"
          />
          <SingleSelectFacetMenu
            label="Series"
            rows={seriesRows}
            value={filters.series || ""}
            onChange={(series) => onPatchFilters({ series })}
            testId="stacks-series-menu"
          />
          {showGenres ? (
            <SingleSelectFacetMenu
              label="Genre"
              rows={genreRows}
              value={filters.genre || ""}
              onChange={(genre) => onPatchFilters({ genre })}
              testId="stacks-genre-menu"
            />
          ) : null}
          {browseHasActiveFilters(filters) ? (
            <button
              type="button"
              className="stacks-clear"
              onClick={() => onPatchFilters({ kind: "", author: "", letter: "", series: "", genre: "", shelf: "" })}
              data-testid="stacks-clear"
            >
              Clear filters
            </button>
          ) : null}
        </div>
      </details>
      <div className="stacks-sort-group">
        <label className="field-inline">
          <span>Sort</span>
          <select
            value={filters.sort}
            data-testid="stacks-sort"
            onChange={(event) => onPatchFilters(sortChangePatch(event.target.value))}
          >
            {BROWSE_SORT_OPTIONS.map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          className="stacks-sort-dir"
          aria-label={`Sort ${sortDirLabel(filters.sort_dir === "asc" ? "desc" : "asc")}`}
          data-testid="stacks-sort-dir"
          onClick={() => onPatchFilters({ sort_dir: filters.sort_dir === "asc" ? "desc" : "asc" })}
        >
          {filters.sort_dir === "asc" ? "↑ Asc" : "↓ Desc"}
        </button>
        <div className="stacks-view-toggle" role="group" aria-label="View">
          <button
            type="button"
            className={view === "covers" ? "is-active" : ""}
            onClick={() => onViewChange("covers")}
            data-testid="stacks-view-covers"
          >
            Covers
          </button>
          <button
            type="button"
            className={view === "list" ? "is-active" : ""}
            onClick={() => onViewChange("list")}
            data-testid="stacks-view-list"
          >
            List
          </button>
        </div>
        <label className="field-inline">
          <span>Per page</span>
          <select
            value={String(pageSize)}
            data-testid="stacks-page-size"
            onChange={(event) => onPageSizeChange(Number(event.target.value))}
          >
            {BROWSE_PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
        {view === "list" ? <ColumnsMenu columns={listColumns} onToggle={onToggleColumn} /> : null}
        <ExportMenu filters={filters} columns={listColumns} />
      </div>
      <details className="stacks-name-shelf">
        <summary className="stacks-name-shelf-toggle" role="button" data-testid="stacks-name-shelf">
          Name a shelf
        </summary>
        <NamedShelves presence={shelfPresence} onChanged={onShelfNamed} />
      </details>
    </div>
  );
}
