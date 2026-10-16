import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import {
  applyBrowseFilterPatch,
  browseCountLine,
  browseFiltersFromSearchParams,
  browseHasActiveFilters,
  browseKinds,
  browseParamsObject,
} from "../browse.js";
import CoverCard from "./CoverCard.jsx";
import WarmLoad from "./WarmLoad.jsx";
import { humanError } from "../copy.js";

const PAGE_SIZE = 48;
const LOADING_LINE = "Loading the shelves.";
const SORTS = [
  ["author", "Author"],
  ["title", "Title"],
  ["updated", "Recently added"],
];

/** Kind, shelf, and sort, then the covers. */
export default function HallCollection({ role = "reader", favoritesAvailable = false }) {
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => browseFiltersFromSearchParams(params), [params]);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const showFavorites = favoritesAvailable || filters.shelf === "favorites";

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError("");
    setOffset(0);
    api
      .browse({ ...filters, offset: 0, limit: PAGE_SIZE })
      .then((data) => {
        if (!alive) return;
        setItems(data.items || []);
        setTotal(data.total || 0);
        setOffset(data.items?.length || 0);
        setLoading(false);
      })
      .catch((err) => {
        if (!alive) return;
        setError(humanError(err));
        setItems([]);
        setTotal(0);
        setLoading(false);
      });
    return () => {
      alive = false;
    };
  }, [filters.kind, filters.author, filters.letter, filters.series, filters.shelf, filters.sort, filters.genre]);

  function patchFilters(patch) {
    setParams(browseParamsObject(applyBrowseFilterPatch(filters, patch)));
  }

  async function loadMore() {
    if (loadingMore || items.length >= total) return;
    setLoadingMore(true);
    try {
      const data = await api.browse({ ...filters, offset, limit: PAGE_SIZE });
      setItems((current) => [...current, ...(data.items || [])]);
      setOffset((current) => current + (data.items?.length || 0));
      setTotal(data.total || 0);
    } catch (err) {
      setError(humanError(err));
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <section className="hall-collection" data-testid="hall-collection">
      <div className="chip-row hall-filters" data-testid="hall-filters">
        <button
          type="button"
          className={`chip${!filters.kind ? " is-on" : ""}`}
          onClick={() => patchFilters({ kind: "" })}
        >
          All
        </button>
        {browseKinds().map((kind) => (
          <button
            key={kind}
            type="button"
            className={`chip${filters.kind === kind ? " is-on" : ""}`}
            onClick={() => patchFilters({ kind })}
          >
            {kind}
          </button>
        ))}
        {showFavorites ? (
          <button
            type="button"
            className={`chip${filters.shelf === "favorites" ? " is-on" : ""}`}
            data-testid="hall-favorites-filter"
            onClick={() => patchFilters({ shelf: filters.shelf === "favorites" ? "" : "favorites" })}
          >
            Favorites
          </button>
        ) : null}
        {SORTS.map(([value, label]) => (
          <button
            key={value}
            type="button"
            className={`chip${filters.sort === value ? " is-on" : ""}`}
            onClick={() => patchFilters({ sort: value })}
          >
            {label}
          </button>
        ))}
        {browseHasActiveFilters(filters) ? (
          <Link className="chip" to="/" data-testid="hall-clear-filters">
            Clear
          </Link>
        ) : null}
      </div>
      {error ? <p className="alert hall-alert">{error}</p> : null}
      <p className="browse-count muted" data-testid="hall-count">
        {loading ? LOADING_LINE : browseCountLine({ kind: filters.kind, shelf: filters.shelf, total, loading: false })}
      </p>
      {loading ? (
        <WarmLoad message={LOADING_LINE} longMessage={LOADING_LINE} testId="hall-collection-loading" />
      ) : items.length ? (
        <div className="browse-grid" data-testid="hall-grid">
          {items.map((work) => (
            <CoverCard key={work.id} work={work} role={role} />
          ))}
        </div>
      ) : (
        <p className="lede browse-empty">Nothing on the shelves yet.</p>
      )}
      {!loading && items.length < total ? (
        <div className="cta-row compact browse-more">
          <button type="button" className="cta compact" onClick={loadMore} disabled={loadingMore}>
            {loadingMore ? "Loading…" : "Show more"}
          </button>
        </div>
      ) : null}
    </section>
  );
}
