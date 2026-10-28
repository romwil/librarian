import { useEffect, useMemo, useState } from "react";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import {
  applyBrowseFilterPatch,
  browseCountLine,
  browseFiltersFromSearchParams,
  browseHeading,
  browseParamsObject,
  loadBrowseListColumns,
  loadBrowseView,
  mergeFacetSelection,
  saveBrowseView,
  toggleBrowseListColumn,
} from "../browse.js";
import BrowseListView from "../components/BrowseListView.jsx";
import CoverCard from "../components/CoverCard.jsx";
import StacksCommandBar from "../components/StacksCommandBar.jsx";
import WarmLoad from "../components/WarmLoad.jsx";
import { ThinkingButton } from "../components/Thinking.jsx";
import { humanError } from "../copy.js";

const DEFAULT_PAGE_SIZE = 48;

export default function BrowsePage() {
  const { user } = useOutletContext() || {};
  const role = user?.role || "reader";
  const [params, setParams] = useSearchParams();
  const filters = useMemo(() => browseFiltersFromSearchParams(params), [params]);
  const [facets, setFacets] = useState(null);
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState("");
  const [view, setView] = useState(() => loadBrowseView());
  const [listColumns, setListColumns] = useState(() => loadBrowseListColumns());
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [namedShelves, setNamedShelves] = useState([]);
  const [shelfPresence, setShelfPresence] = useState("");
  const [shelfTick, setShelfTick] = useState(0);

  const authorChips = useMemo(
    () => mergeFacetSelection(facets?.authors, filters.author, { limit: 40 }),
    [facets, filters.author],
  );
  const seriesChips = useMemo(
    () => mergeFacetSelection(facets?.series, filters.series, { limit: 40 }),
    [facets, filters.series],
  );
  const genreChips = useMemo(
    () => mergeFacetSelection(facets?.genres, filters.genre, { limit: 40 }),
    [facets, filters.genre],
  );
  const showGenres = Boolean(facets?.genre_ready) || Boolean(filters.genre);

  useEffect(() => {
    let alive = true;
    api
      .shelves()
      .then((data) => {
        if (!alive) return;
        setNamedShelves(Array.isArray(data?.shelves) ? data.shelves : []);
        setShelfPresence(String(data?.presence || ""));
      })
      .catch(() => {
        if (!alive) return;
        setNamedShelves([]);
        setShelfPresence("");
      });
    return () => {
      alive = false;
    };
  }, [shelfTick]);

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
      .browse({
        kind: filters.kind,
        author: filters.author,
        letter: filters.letter,
        series: filters.series,
        shelf: filters.shelf,
        sort: filters.sort,
        sort_dir: filters.sort_dir,
        genre: filters.genre,
        offset: 0,
        limit: pageSize,
      })
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
  }, [
    filters.kind,
    filters.author,
    filters.letter,
    filters.series,
    filters.shelf,
    filters.sort,
    filters.sort_dir,
    filters.genre,
    pageSize,
  ]);

  function patchFilters(patch) {
    setParams(browseParamsObject(applyBrowseFilterPatch(filters, patch)));
  }

  function changeView(next) {
    setView(saveBrowseView(next));
  }

  function toggleColumn(column) {
    setListColumns((current) => toggleBrowseListColumn(current, column));
  }

  function changePageSize(next) {
    setPageSize(Number(next) || DEFAULT_PAGE_SIZE);
  }

  async function loadMore() {
    if (loadingMore || items.length >= total) return;
    setLoadingMore(true);
    try {
      const data = await api.browse({ ...filters, offset, limit: pageSize });
      setItems((current) => [...current, ...(data.items || [])]);
      setOffset((current) => current + (data.items?.length || 0));
      setTotal(data.total || 0);
    } catch (err) {
      setError(humanError(err));
    } finally {
      setLoadingMore(false);
    }
  }

  const activeShelf = namedShelves.find((shelf) => shelf.id === filters.shelf);
  const heading = browseHeading(filters, activeShelf?.name || "");

  function onShelfNamed(shelf) {
    setShelfTick((value) => value + 1);
    if (shelf?.id) patchFilters({ shelf: shelf.id });
  }

  return (
    <div className="browse-page page-settle" data-testid="browse-page">
      <section className="browse-hero">
        <p className="kicker">Stacks</p>
        <h1>{heading}</h1>
        <p className="lede">
          Browse by author, kind, or series — no search required.{" "}
          <Link to="/wanted">Wanted</Link> keeps what is still missing.
        </p>
        <StacksCommandBar
          filters={filters}
          onPatchFilters={patchFilters}
          view={view}
          onViewChange={changeView}
          listColumns={listColumns}
          onToggleColumn={toggleColumn}
          pageSize={pageSize}
          onPageSizeChange={changePageSize}
          authorRows={authorChips}
          seriesRows={seriesChips}
          genreRows={genreChips}
          showGenres={showGenres}
          shelves={namedShelves}
          shelfPresence={shelfPresence}
          onShelfNamed={onShelfNamed}
        />
      </section>
      {error ? <p className="alert hall-alert">{error}</p> : null}
      <section className="browse-grid-wrap">
        <p className="browse-count muted" data-testid="browse-count">
          {browseCountLine({ kind: filters.kind, shelf: filters.shelf, total, loading })}
        </p>
        {loading ? (
          <WarmLoad message="Warming the lamp on these stacks…" testId="browse-loading" />
        ) : items.length ? (
          view === "list" ? (
            <BrowseListView items={items} columns={listColumns} />
          ) : (
            <div className="browse-grid" data-testid="browse-grid">
              {items.map((work) => (
                <CoverCard key={work.id} work={work} role={role} cardMode="stacks" />
              ))}
            </div>
          )
        ) : (
          <p className="lede browse-empty">Nothing matches these shelves yet.</p>
        )}
        {!loading && items.length < total ? (
          <div className="cta-row compact browse-more">
            <ThinkingButton type="button" className="cta outline compact" onClick={loadMore} busy={loadingMore}>
              Show more
            </ThinkingButton>
          </div>
        ) : null}
      </section>
    </div>
  );
}
