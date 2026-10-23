import { useEffect, useMemo, useState } from "react";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { saveBeyondGet } from "../beyondGet.js";
import CoverCard from "../components/CoverCard.jsx";
import QueryForm from "../components/QueryForm.jsx";
import Rail from "../components/Rail.jsx";
import SearchModeControl, { normalizeSearchMode } from "../components/SearchModeControl.jsx";
import {
  FIELD_HELP,
  TRENDING_BOOKS_LABEL,
  discoverKindNote,
  discoverStatusLine,
  humanError,
  searchStatusLine,
} from "../copy.js";
import {
  DISCOVER_BROWSE_LIMIT,
  buildFindSearchParams,
  composeSearchQuery,
  discoverCatFromSearchParams,
  discoverHref,
  emptyFindFields,
  findFieldsFromSearchParams,
  findKindOptions,
  groupDiscoverCategories,
  groupDiscoverRails,
  pruneFieldsForKind,
  shouldShowDiscover,
} from "../find.js";
import { didYouMeanList, didYouMeanPresence, searchForgave } from "../lib/searchForgive.js";
import {
  FORMAT_FACETS,
  WHERE_FACETS,
  applySearchFacets,
  countSearchFacets,
  emptyFacetSelection,
  yearFacetEntries,
} from "../searchFacets.js";

function fieldsFromState(draft, kind, advanced) {
  return pruneFieldsForKind(kind, {
    ...emptyFindFields(),
    ...advanced,
    q: draft,
    kind,
  });
}

function FacetGroup({ legend, options, value, onChange, counts, always }) {
  const visible = options.filter(([key]) => always || value === key || (counts[key] || 0) > 0);
  if (!visible.length) return null;
  return (
    <fieldset className="search-facet">
      <legend>{legend}</legend>
      <ul className="search-facet-list">
        {visible.map(([key, label]) => {
          const n = counts[key] || 0;
          const on = value === key;
          return (
            <li key={key}>
              <button
                type="button"
                className={`chip${on ? " is-on" : ""}`}
                aria-pressed={on}
                onClick={() => onChange(on ? "" : key)}
              >
                {label}
                {n ? <span className="search-facet-count">{n}</span> : null}
              </button>
            </li>
          );
        })}
      </ul>
    </fieldset>
  );
}

function SkeletonRail({ label = "Warming the lamp…" }) {
  return (
    <div className="skeleton-rail" data-testid="skeleton-rail" aria-hidden="true">
      <p className="skeleton-rail-label">{label}</p>
      <div className="skeleton-rail-track">
        {[0, 1, 2, 3, 4].map((n) => (
          <span key={n} className="skeleton-cover" />
        ))}
      </div>
    </div>
  );
}

export default function SearchPage() {
  const [params, setParams] = useSearchParams();
  const { user, features } = useOutletContext();
  const showExtra = Boolean(features?.show_extra_categories);
  const kindOptions = findKindOptions(showExtra);
  const fields = findFieldsFromSearchParams(params);
  const mode = normalizeSearchMode(params.get("mode"));
  const discoverCat = discoverCatFromSearchParams(params);
  const activeMode = mode || "title";
  const composed = composeSearchQuery(fields);
  const [draft, setDraft] = useState(fields.q);
  const [kind, setKind] = useState(fields.kind);
  const [advanced, setAdvanced] = useState(() => fieldsFromState(fields.q, fields.kind, fields));
  const [result, setResult] = useState({ local: [] });
  const [phase, setPhase] = useState("idle");
  const [error, setError] = useState("");
  const [facet, setFacet] = useState(emptyFacetSelection);
  const [discover, setDiscover] = useState({ items: [], categories: [], limit: 0 });
  const [discoverPhase, setDiscoverPhase] = useState("idle");
  const [discoverError, setDiscoverError] = useState("");
  const [jobs, setJobs] = useState({});
  const openDiscover = shouldShowDiscover(fields);
  const browsing = Boolean(discoverCat) && openDiscover;

  useEffect(() => {
    const next = fieldsFromState(fields.q, fields.kind, fields);
    setDraft(next.q);
    setKind(next.kind);
    setAdvanced(next);
  }, [fields.q, fields.kind, fields.author, fields.title, fields.isbn, fields.series, fields.year, fields.issue, fields.artist, fields.album]);

  useEffect(() => {
    setFacet(emptyFacetSelection());
  }, [composed, fields.kind, mode, fields.author, fields.title, fields.isbn, fields.series, fields.year, fields.issue, fields.artist, fields.album]);

  useEffect(() => {
    if (!composed) {
      setResult({ local: [] });
      setPhase("idle");
      setError("");
      return undefined;
    }
    let alive = true;
    setPhase("local");
    setError("");
    api
      .search(composed, { beyond: true, kind: fields.kind, mode, ...fields })
      .then((data) => {
        if (!alive) return;
        setResult({
          local: data.local || [],
          beyond: data.beyond || [],
          public_domain: data.public_domain || [],
          did_you_mean: data.did_you_mean || [],
          forgave: Boolean(data.forgave),
        });
        setPhase("done");
      })
      .catch((err) => {
        if (!alive) return;
        setError(humanError(err));
        setPhase("error");
      });
    return () => {
      alive = false;
    };
  }, [composed, fields.kind, mode, fields.author, fields.title, fields.isbn, fields.series, fields.year, fields.issue, fields.artist, fields.album]);

  useEffect(() => {
    let alive = true;
    setDiscoverPhase("loading");
    setDiscoverError("");
    const extras = { kind: fields.kind, cat: discoverCat };
    if (discoverCat) extras.limit = DISCOVER_BROWSE_LIMIT;
    api
      .discover(extras)
      .then((data) => {
        if (!alive) return;
        setDiscover({
          items: data.items || [],
          categories: data.categories || [],
          limit: data.limit || 0,
        });
        if (data.beyond_error) {
          setDiscoverError(humanError(data.beyond_error));
          setDiscoverPhase((data.items || []).length ? "done" : "error");
        } else {
          setDiscoverPhase("done");
        }
      })
      .catch((err) => {
        if (!alive) return;
        setDiscoverError(humanError(err));
        setDiscoverPhase("error");
      });
    return () => {
      alive = false;
    };
  }, [fields.kind, discoverCat]);

  function commitSearch(nextKind = kind, nextAdvanced = advanced, nextMode = activeMode) {
    const next = fieldsFromState(draft, nextKind, nextAdvanced);
    setKind(next.kind);
    setAdvanced(next);
    const query = buildFindSearchParams(next);
    query.set("mode", nextMode);
    setParams(query);
  }

  function onMode(nextMode) {
    const chosen = normalizeSearchMode(nextMode) || "title";
    if (draft.trim() || composed) {
      commitSearch(kind, advanced, chosen);
      return;
    }
    const query = buildFindSearchParams(fieldsFromState(draft, kind, advanced));
    query.set("mode", chosen);
    setParams(query);
  }

  async function shelveEdition(edition) {
    setError("");
    try {
      const data = await api.shelvePublicDomain(edition);
      setResult((prev) => ({
        ...prev,
        public_domain: (prev.public_domain || []).map((row) =>
          row.download_url === edition.download_url
            ? { ...row, shelved: true, work_id: data.work_id }
            : row,
        ),
      }));
    } catch (err) {
      setError(humanError(err));
    }
  }

  function onKindCommit(nextKind) {
    const next = fieldsFromState(draft, nextKind, advanced);
    setKind(next.kind);
    setAdvanced(next);
    if (draft.trim() || composed) {
      const query = buildFindSearchParams(next);
      if (mode) query.set("mode", mode);
      setParams(query);
      return;
    }
    setParams(discoverParams(next.kind, ""));
  }

  function discoverParams(nextKind, nextCat) {
    const next = {};
    if (nextKind) next.kind = nextKind;
    if (nextCat) next.discover = nextCat;
    return next;
  }

  function onDidYouMean(title) {
    setDraft(title);
    const next = fieldsFromState(title, kind, advanced);
    setKind(next.kind);
    setAdvanced(next);
    const query = buildFindSearchParams(next);
    if (mode) query.set("mode", mode);
    setParams(query);
  }

  async function request(item) {
    const key = item.guid || item.title;
    if (jobs[key]) {
      return { job: { status: jobs[key] }, wanted: { id: jobs[key], status: jobs[key] === "asked" ? "asked" : "wanted" } };
    }
    const data = await saveBeyondGet(item);
    const status = data.jobStatus === "saved" ? "saved" : "asked";
    setJobs((prev) => ({ ...prev, [key]: status }));
    return { job: { status: data.jobStatus === "asked" ? "asked" : "saved" }, wanted: data.wanted };
  }

  const status = searchStatusLine({
    q: composed,
    kind: composed ? fields.kind : kind,
    localCount: result.local?.length || 0,
    phase,
  });
  const suggestions = didYouMeanList(result);
  const forgiveNote = didYouMeanPresence(suggestions);
  const counts = countSearchFacets(result);
  const filtered = applySearchFacets(result, facet);
  const yearEntries = yearFacetEntries(counts.years);
  const yearOptions = yearEntries.map(([year, count]) => [year, year]);
  const yearCounts = Object.fromEntries(yearEntries);
  const beyondItems = (filtered.beyond || []).map((item) => ({
    ...item,
    job_status: jobs[item.guid || item.title] === "asked" ? "asked" : item.job_status,
    wanted:
      jobs[item.guid || item.title] === "saved"
        ? { id: "saved", status: "wanted" }
        : item.wanted,
  }));
  const discoverItems = (discover.items || []).map((item) => ({
    ...item,
    job_status: jobs[item.guid || item.title] === "asked" ? "asked" : item.job_status,
    wanted:
      jobs[item.guid || item.title] === "saved"
        ? { id: "saved", status: "wanted" }
        : item.wanted,
  }));
  const discoverEmpty = discoverStatusLine({
    kind: fields.kind,
    phase: discoverPhase === "loading" ? "loading" : discoverPhase === "error" ? "error" : "done",
    count: discoverItems.length,
  });
  const kindCats = useMemo(
    () => (discover.categories || []).filter((row) => !fields.kind || row.kind === fields.kind),
    [discover.categories, fields.kind],
  );
  const rails = groupDiscoverRails(discoverItems, discover.categories);
  const browseTitle =
    kindCats.find((row) => String(row.id) === String(discoverCat))?.name ||
    discoverItems[0]?.category_name ||
    discoverCat;
  const backDiscoverHref = discoverHref({ kind: fields.kind });
  const getKicker = "Get saves a slip. Confirm on Downloads before SAB.";

  function renderDiscoverBrowse() {
    return (
      <section className="discover-browse" data-testid="discover-browse">
        <header className="discover-browse-head">
          <Link className="discover-back" to={backDiscoverHref}>
            ← Discover
          </Link>
          <h2>{browseTitle || "Category"}</h2>
          <p>{getKicker}</p>
        </header>
        {discoverPhase === "loading" && !discoverItems.length ? (
          <SkeletonRail label="The indexers are turning pages…" />
        ) : null}
        {discoverItems.length ? (
          <div className="discover-grid" data-testid="discover-grid">
            {discoverItems.map((item) => (
              <CoverCard
                key={item.id || item.guid || item.title}
                work={item}
                onRequest={request}
                beyond
                role={user?.role}
              />
            ))}
          </div>
        ) : discoverPhase !== "loading" ? (
          <p className="lede discover-empty">{discoverEmpty}</p>
        ) : null}
      </section>
    );
  }

  function renderDiscoverRails() {
    if (discoverPhase === "loading" && !rails.length) {
      return <SkeletonRail label="Warming Discover…" />;
    }
    if (!rails.length) {
      return <p className="lede discover-empty">{discoverEmpty}</p>;
    }
    return rails.map((rail) => {
      const feedKind =
        (discover.categories || []).find((row) => String(row.id) === String(rail.id))?.kind || fields.kind;
      return (
        <Rail
          key={rail.id}
          title={rail.title}
          kicker={getKicker}
          items={rail.items}
          onRequest={request}
          beyond
          role={user?.role}
          seeAllTo={discoverHref({ discover: rail.id, kind: feedKind || fields.kind })}
        />
      );
    });
  }

  function renderDiscover() {
    return (
      <section className="discover-panel" data-testid="discover-panel">
        <header className="discover-head">
          <h2>Discover</h2>
          <p className="lede discover-lede">{discoverKindNote(fields.kind)}</p>
        </header>
        {kindCats.length > 1 ? (
          <div className="discover-cats" data-testid="discover-cats">
            <div className="search-hero chip-row discover-cats-all">
              <button
                type="button"
                className={`chip${discoverCat === "" ? " is-on" : ""}`}
                aria-pressed={discoverCat === ""}
                onClick={() => setParams(discoverParams(fields.kind, ""))}
              >
                All
              </button>
            </div>
            {groupDiscoverCategories(kindCats).map((group) => (
              <div key={group.id} className="discover-cat-group" data-parent={group.id}>
                <p className="discover-cat-label kicker">{group.name}</p>
                <div className="search-hero chip-row">
                  {group.categories.map((row) => (
                    <button
                      key={row.id}
                      type="button"
                      className={`chip${discoverCat === String(row.id) ? " is-on" : ""}`}
                      aria-pressed={discoverCat === String(row.id)}
                      onClick={() => setParams(discoverParams(fields.kind || row.kind, String(row.id)))}
                    >
                      {row.name}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        ) : null}
        {discoverError ? (
          <p className="callout" role="status" data-testid="discover-error">
            {discoverError}
          </p>
        ) : null}
        {browsing ? renderDiscoverBrowse() : renderDiscoverRails()}
      </section>
    );
  }

  return (
    <div className="search-page page-settle">
      <h1 className="sr-only">Search</h1>
      <QueryForm
        inputId="find-search"
        draft={draft}
        onDraft={setDraft}
        kind={kind}
        onKindCommit={onKindCommit}
        advanced={advanced}
        onAdvanced={setAdvanced}
        onSubmit={() => commitSearch()}
        placeholder="Title, author, or ISBN"
        ariaLabel="Search"
        kindHelp={FIELD_HELP.searchKind}
        advancedSummary="More ways to search"
        showKindChips
        advancedOpen
        kinds={kindOptions}
      />
      {!composed ? (
        <>
          <p className="search-noted-door muted" data-testid="trending-books-door">
            <Link to="/noted">{TRENDING_BOOKS_LABEL}</Link>
            {" / "}
            <Link to="/noted">New & noted</Link>
          </p>
          {renderDiscover()}
        </>
      ) : (
        <div className="search-with-facets">
          <aside className="search-facets" aria-label="Filters">
            <FacetGroup
              legend="Format"
              options={FORMAT_FACETS}
              value={facet.format}
              onChange={(format) => setFacet((prev) => ({ ...prev, format }))}
              counts={counts.formats}
            />
            <FacetGroup
              legend="Where"
              options={WHERE_FACETS}
              value={facet.where}
              onChange={(where) => setFacet((prev) => ({ ...prev, where }))}
              counts={counts.where}
              always
            />
            {yearEntries.length ? (
              <FacetGroup
                legend="Year"
                options={yearOptions}
                value={facet.year}
                onChange={(year) => setFacet((prev) => ({ ...prev, year }))}
                counts={yearCounts}
              />
            ) : null}
          </aside>
          <div className="search-results">
            <SearchModeControl mode={activeMode} onMode={onMode} />
            <p className="search-status" aria-live="polite" data-testid="search-status">
              {status}
              {searchForgave(result) ? " · matched a close spelling" : ""}
            </p>
            {error ? (
              <p className="callout" role="status" data-testid="search-error">
                {error}
              </p>
            ) : null}
            {suggestions.length ? (
              <div className="search-forgive" data-testid="search-did-you-mean">
                <p className="kicker">{forgiveNote}</p>
                <div className="cta-row">
                  {suggestions.map((title) => (
                    <button
                      key={title}
                      type="button"
                      className="cta outline compact"
                      onClick={() => onDidYouMean(title)}
                    >
                      {title}
                    </button>
                  ))}
                </div>
              </div>
            ) : null}
            <Rail
              title="On the shelf"
              kicker={phase === "local" ? "Searching…" : "Local catalog · click cover to peek"}
              items={filtered.local}
              empty={phase === "local" ? "Searching…" : "Nothing on the shelf yet."}
              role={user?.role}
            />
            <section id="beyond" className="search-beyond" data-testid="search-beyond">
              <h2>Beyond</h2>
              <Rail
                title="Usenet"
                kicker="NZBFinder and the extra indexers in Settings"
                items={beyondItems}
                empty={phase === "local" ? "Looking beyond the shelves…" : "Nothing on Usenet for this search."}
                beyond
                onRequest={request}
                role={user?.role}
              />
              <div className="public-domain-lane" data-testid="public-domain-lane">
                <p className="kicker">Public domain</p>
                {(filtered.public_domain || []).length ? (
                  <ul>
                    {(filtered.public_domain || []).map((edition) => (
                      <li key={`${edition.source}-${edition.id || edition.download_url}`}>
                        <span>
                          {edition.title}
                          {edition.author ? ` · ${edition.author}` : ""} ·{" "}
                          {edition.source === "standard_ebooks" ? "Standard Ebooks" : "Project Gutenberg"}
                        </span>
                        {edition.shelved ? (
                          <span>On the shelf</span>
                        ) : (
                          <button type="button" className="cta compact" onClick={() => shelveEdition(edition)}>
                            Shelve
                          </button>
                        )}
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="muted">No public-domain edition matches this search.</p>
                )}
              </div>
            </section>
            <details className="discover-fold">
              <summary className="kicker">Discover — trending on the indexers</summary>
              {renderDiscover()}
            </details>
          </div>
        </div>
      )}
    </div>
  );
}
