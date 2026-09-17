import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import {
  BROWSE_LETTERS,
  applyBrowseFilterPatch,
  browseFiltersFromSearchParams,
  browseHasActiveFilters,
  browseHeading,
  browseKinds,
  browseParamsObject,
  mergeFacetSelection,
  readBrowseFoldState,
  toggleBrowseFold,
} from "../browse.js";
import CoverCard from "../components/CoverCard.jsx";
import { humanError } from "../copy.js";

const PAGE_SIZE = 48;

function BrowseFacetFold({ id, label, open, activeLabel, onToggle, children, testId }) {
  return (
    <div className={`browse-fold${open ? " is-open" : ""}`} data-testid={testId || `browse-fold-${id}`}>
      <button
        type="button"
        className="browse-fold-toggle"
        aria-expanded={open}
        onClick={onToggle}
      >
        <span className="browse-fold-label">{label}</span>
        {activeLabel && !open ? <span className="browse-fold-active muted">{activeLabel}</span> : null}
        <span className="browse-fold-chevron" aria-hidden="true">
          {open ? "▾" : "▸"}
        </span>
      </button>
      {open ? <div className="browse-fold-body">{children}</div> : null}
    </div>
  );
}

export default function BrowsePage() {
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => browseFiltersFromSearchParams(params), [params]);
  const [facets, setFacets] = useState(null);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [folds, setFolds] = useState(() => readBrowseFoldState());

  const letterCounts = useMemo(() => {
    const map = new Map();
    for (const row of facets?.letters || []) {
      map.set(row.letter, row.count);
    }
    return map;
  }, [facets]);

  const seriesChips = useMemo(
    () => mergeFacetSelection(facets?.series, filters.series, { limit: 16 }),
    [facets, filters.series],
  );
  const genreChips = useMemo(
    () => mergeFacetSelection(facets?.genres, filters.genre, { limit: 12 }),
    [facets, filters.genre],
  );
  const authorChips = useMemo(
    () => mergeFacetSelection(facets?.authors, filters.author, { limit: 12 }),
    [facets, filters.author],
  );

  useEffect(() => {
    let alive = true;
    api
      .browseFacets({ kind: filters.kind, shelf: filters.shelf })
      .then((data) => {
        if (alive) setFacets(data);
      })
      .catch(() => {
        if (alive) setFacets(null);
      });
    return () => {
      alive = false;
    };
  }, [filters.kind, filters.shelf]);

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

  function flipFold(id) {
    setFolds((current) => toggleBrowseFold(current, id));
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

  const heading = browseHeading(filters);
  const showGenres = Boolean(facets?.genre_ready) || Boolean(filters.genre);

  return (
    <div className="browse-page" data-testid="browse-page">
      <section className="browse-hero">
        <p className="kicker">Stacks</p>
        <h1>{heading}</h1>
        <p className="lede">Browse by author, kind, or series — no search required.</p>
        <div className="chip-row browse-kinds" data-testid="browse-kinds">
          <button
            type="button"
            className={`chip${!filters.kind ? " is-on" : ""}`}
            onClick={() => patchFilters({ kind: "" })}
          >
            All kinds
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
          <button
            type="button"
            className={`chip${filters.shelf === "favorites" ? " is-on" : ""}`}
            onClick={() =>
              patchFilters({ shelf: filters.shelf === "favorites" ? "" : "favorites" })
            }
          >
            Favorites
          </button>
        </div>
        <div className="browse-letters" data-testid="browse-letters" role="navigation" aria-label="Author A to Z">
          {BROWSE_LETTERS.map((letter) => {
            const count = letterCounts.get(letter) || 0;
            const on = filters.letter === letter;
            return (
              <button
                key={letter}
                type="button"
                className={`browse-letter${on ? " is-on" : ""}`}
                disabled={!count && !on}
                onClick={() => patchFilters({ letter: on ? "" : letter })}
              >
                {letter}
              </button>
            );
          })}
        </div>
        {authorChips.length ? (
          <BrowseFacetFold
            id="author"
            label="Authors"
            open={Boolean(folds.author) || Boolean(filters.author)}
            activeLabel={filters.author || ""}
            onToggle={() => flipFold("author")}
            testId="browse-authors-fold"
          >
            <div className="chip-row browse-authors" data-testid="browse-authors">
              <button
                type="button"
                className={`chip${!filters.author ? " is-on" : ""}`}
                onClick={() => patchFilters({ author: "" })}
              >
                Any author
              </button>
              {authorChips.map((row) => (
                <button
                  key={row.name}
                  type="button"
                  className={`chip${filters.author.toLowerCase() === row.name.toLowerCase() ? " is-on" : ""}`}
                  onClick={() =>
                    patchFilters({
                      author: filters.author.toLowerCase() === row.name.toLowerCase() ? "" : row.name,
                    })
                  }
                >
                  {row.name}
                  {row.count != null ? <span className="muted"> {row.count}</span> : null}
                </button>
              ))}
            </div>
          </BrowseFacetFold>
        ) : null}
        {seriesChips.length || filters.series ? (
          <BrowseFacetFold
            id="series"
            label="Series"
            open={Boolean(folds.series) || Boolean(filters.series)}
            activeLabel={filters.series || ""}
            onToggle={() => flipFold("series")}
            testId="browse-series-fold"
          >
            <div className="chip-row browse-series" data-testid="browse-series">
              <button
                type="button"
                className={`chip${!filters.series ? " is-on" : ""}`}
                onClick={() => patchFilters({ series: "" })}
              >
                Any series
              </button>
              {seriesChips.map((row) => (
                <button
                  key={row.name}
                  type="button"
                  className={`chip${filters.series.toLowerCase() === row.name.toLowerCase() ? " is-on" : ""}`}
                  onClick={() =>
                    patchFilters({
                      series: filters.series.toLowerCase() === row.name.toLowerCase() ? "" : row.name,
                    })
                  }
                >
                  {row.name}
                  {row.count != null ? <span className="muted"> {row.count}</span> : null}
                </button>
              ))}
            </div>
          </BrowseFacetFold>
        ) : null}
        <BrowseFacetFold
          id="genre"
          label="Genres"
          open={Boolean(folds.genre) || Boolean(filters.genre)}
          activeLabel={filters.genre || ""}
          onToggle={() => flipFold("genre")}
          testId="browse-genre-fold"
        >
          <div className="chip-row browse-genre-stub" data-testid="browse-genre-stub">
            {showGenres && (genreChips.length || filters.genre) ? (
              <>
                <button
                  type="button"
                  className={`chip${!filters.genre ? " is-on" : ""}`}
                  onClick={() => patchFilters({ genre: "" })}
                >
                  Any genre
                </button>
                {genreChips.map((row) => (
                  <button
                    key={row.name}
                    type="button"
                    className={`chip${filters.genre.toLowerCase() === row.name.toLowerCase() ? " is-on" : ""}`}
                    onClick={() =>
                      patchFilters({
                        genre: filters.genre.toLowerCase() === row.name.toLowerCase() ? "" : row.name,
                      })
                    }
                  >
                    {row.name}
                    {row.count != null ? <span className="muted"> {row.count}</span> : null}
                  </button>
                ))}
              </>
            ) : (
              <span className="chip is-disabled" title="Subject enrich fills these later">
                Genre facets soon
              </span>
            )}
          </div>
        </BrowseFacetFold>
        <div className="chip-row browse-sort">
          {[
            ["author", "Author"],
            ["title", "Title"],
            ["updated", "Recently updated"],
          ].map(([value, label]) => (
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
            <Link className="chip" to="/browse" data-testid="browse-clear">
              Clear filters
            </Link>
          ) : null}
        </div>
      </section>
      {error ? <p className="alert hall-alert">{error}</p> : null}
      <section className="browse-grid-wrap">
        <p className="browse-count muted" data-testid="browse-count">
          {loading ? "Opening the stacks…" : `${total} on the shelves`}
        </p>
        {loading ? null : items.length ? (
          <div className="browse-grid" data-testid="browse-grid">
            {items.map((work) => (
              <CoverCard key={work.id} work={work} />
            ))}
          </div>
        ) : (
          <p className="lede browse-empty">Nothing matches these shelves yet.</p>
        )}
        {!loading && items.length < total ? (
          <div className="cta-row compact browse-more">
            <button type="button" className="cta outline compact" onClick={loadMore} disabled={loadingMore}>
              {loadingMore ? "Loading…" : "Show more"}
            </button>
          </div>
        ) : null}
      </section>
    </div>
  );
}
