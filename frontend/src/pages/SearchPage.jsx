import { useEffect, useState } from "react";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import QueryForm from "../components/QueryForm.jsx";
import Rail from "../components/Rail.jsx";
import SearchModeControl, { normalizeSearchMode } from "../components/SearchModeControl.jsx";
import {
  FIELD_HELP,
  TRENDING_BOOKS_LABEL,
  humanError,
  searchStatusLine,
} from "../copy.js";
import {
  buildFindSearchParams,
  composeSearchQuery,
  emptyFindFields,
  findFieldsFromSearchParams,
  pruneFieldsForKind,
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

export default function SearchPage() {
  const [params, setParams] = useSearchParams();
  const { user } = useOutletContext();
  const fields = findFieldsFromSearchParams(params);
  const mode = normalizeSearchMode(params.get("mode"));
  const activeMode = mode || "title";
  const composed = composeSearchQuery(fields);
  const [draft, setDraft] = useState(fields.q);
  const [kind, setKind] = useState(fields.kind);
  const [advanced, setAdvanced] = useState(() => fieldsFromState(fields.q, fields.kind, fields));
  const [result, setResult] = useState({ local: [] });
  const [phase, setPhase] = useState("idle");
  const [error, setError] = useState("");
  const [facet, setFacet] = useState(emptyFacetSelection);

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
    }
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
        showKindChips={false}
      />
      {!composed ? (
        <p className="search-noted-door muted" data-testid="trending-books-door">
          <Link to="/noted">{TRENDING_BOOKS_LABEL}</Link>
          {" / "}
          <Link to="/noted">New & noted</Link>
        </p>
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
                items={filtered.beyond || []}
                empty={phase === "local" ? "Looking beyond the shelves…" : "Nothing on Usenet for this search."}
                beyond
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
          </div>
        </div>
      )}
    </div>
  );
}
