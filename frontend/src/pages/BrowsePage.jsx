import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import {
  BROWSE_LETTERS,
  browseFiltersFromSearchParams,
  browseHref,
  browseKinds,
} from "../browse.js";
import CoverCard from "../components/CoverCard.jsx";
import { humanError } from "../copy.js";

const PAGE_SIZE = 48;

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

  const letterCounts = useMemo(() => {
    const map = new Map();
    for (const row of facets?.letters || []) {
      map.set(row.letter, row.count);
    }
    return map;
  }, [facets]);

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
    const next = { ...filters, ...patch };
    const href = browseHref(next);
    const qs = href.includes("?") ? href.slice(href.indexOf("?") + 1) : "";
    setParams(qs ? Object.fromEntries(new URLSearchParams(qs)) : {});
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

  const titleBits = [];
  if (filters.shelf === "favorites") titleBits.push("Favorites");
  if (filters.kind) titleBits.push(filters.kind);
  if (filters.author) titleBits.push(filters.author);
  if (filters.series) titleBits.push(filters.series);
  if (filters.letter) titleBits.push(`Letter ${filters.letter}`);
  const heading = titleBits.length ? titleBits.join(" · ") : "The stacks";

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
        {(facets?.series || []).length ? (
          <div className="chip-row browse-series" data-testid="browse-series">
            <button
              type="button"
              className={`chip${!filters.series ? " is-on" : ""}`}
              onClick={() => patchFilters({ series: "" })}
            >
              Any series
            </button>
            {(facets.series || []).slice(0, 16).map((row) => (
              <button
                key={row.name}
                type="button"
                className={`chip${filters.series === row.name ? " is-on" : ""}`}
                onClick={() =>
                  patchFilters({ series: filters.series === row.name ? "" : row.name })
                }
              >
                {row.name}
                <span className="muted"> {row.count}</span>
              </button>
            ))}
          </div>
        ) : null}
        <div className="chip-row browse-genre-stub" data-testid="browse-genre-stub">
          {facets?.genre_ready && (facets.genres || []).length ? (
            (facets.genres || []).slice(0, 12).map((row) => (
              <button
                key={row.name}
                type="button"
                className={`chip${filters.genre === row.name ? " is-on" : ""}`}
                onClick={() =>
                  patchFilters({ genre: filters.genre === row.name ? "" : row.name })
                }
              >
                {row.name}
              </button>
            ))
          ) : (
            <span className="chip is-disabled" title="Subject enrich fills these later">
              Genre facets soon
            </span>
          )}
        </div>
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
          {filters.author || filters.letter || filters.series || filters.shelf || filters.kind ? (
            <Link className="chip" to="/browse">
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
