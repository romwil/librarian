import { useEffect, useState } from "react";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { saveBeyondGet } from "../beyondGet.js";
import ConfirmDialog from "../components/ConfirmDialog.jsx";
import CoverCard from "../components/CoverCard.jsx";
import QueryForm from "../components/QueryForm.jsx";
import Rail from "../components/Rail.jsx";
import SearchModeControl, { normalizeSearchMode } from "../components/SearchModeControl.jsx";
import { ThinkingButton } from "../components/Thinking.jsx";
import {
  FIELD_HELP,
  beyondSearchCopy,
  discoverStatusLine,
  humanError,
  localSearchEmpty,
  searchStatusLine,
} from "../copy.js";
import {
  DISCOVER_PAGE_SIZE,
  buildFindSearchParams,
  composeSearchQuery,
  discoverFeedRequest,
  emptyFindFields,
  findFieldsFromSearchParams,
  findKindOptions,
  pruneFieldsForKind,
  searchRequestQuery,
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
import {
  ASK_THE_HOUSE,
  ASK_THE_HOUSE_PROMPT,
  DISCLOSURE_STAY,
  DISCLOSURE_TITLE,
  beyondDisclosureBody,
  rememberDisclosure,
  readerSawDisclosure,
  searchFieldParams,
  shouldAutoBeyond,
} from "../searchLanes.js";

function fieldsFromState(draft, kind, advanced) {
  return pruneFieldsForKind(kind, {
    ...emptyFindFields(),
    ...advanced,
    q: draft,
    kind,
  });
}

/** Property list, so an effect can depend on each field without the object identity. */
function snapshotFindFields(q, kind, author, title, isbn, series, issue, artist, album, year) {
  return { q, kind, author, title, isbn, series, issue, artist, album, year };
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
  const [discoverOpen, setDiscoverOpen] = useState(false);
  const [discoverPage, setDiscoverPage] = useState(0);
  const [discoverPaging, setDiscoverPaging] = useState("");
  const [jobs, setJobs] = useState({});
  const [asked, setAsked] = useState("");
  const [askOpen, setAskOpen] = useState(false);
  const [askBusy, setAskBusy] = useState(false);
  const keeper = shouldAutoBeyond(user?.role);

  useEffect(() => {
    const bag = snapshotFindFields(
      fields.q,
      fields.kind,
      fields.author,
      fields.title,
      fields.isbn,
      fields.series,
      fields.issue,
      fields.artist,
      fields.album,
      fields.year,
    );
    const next = fieldsFromState(fields.q, fields.kind, bag);
    setDraft(next.q);
    setKind(next.kind);
    setAdvanced(next);
  }, [fields.q, fields.kind, fields.author, fields.title, fields.isbn, fields.series, fields.year, fields.issue, fields.artist, fields.album]);

  useEffect(() => {
    setFacet(emptyFacetSelection());
  }, [composed, fields.kind, mode, fields.author, fields.title, fields.isbn, fields.series, fields.year, fields.issue, fields.artist, fields.album]);

  useEffect(() => {
    if (!composed) {
      setResult({ local: [], beyond: [], public_domain: [], beyond_error: "" });
      setPhase("idle");
      setError("");
      setAsked("");
      return undefined;
    }
    let alive = true;
    setPhase("local");
    setError("");
    setAsked("");
    const bag = snapshotFindFields(
      fields.q,
      fields.kind,
      fields.author,
      fields.title,
      fields.isbn,
      fields.series,
      fields.issue,
      fields.artist,
      fields.album,
      fields.year,
    );
    const extras = searchFieldParams(bag, { mode });
    api
      .search(searchRequestQuery(bag), extras)
      .then((data) => {
        if (!alive) return;
        setResult({
          local: data.local || [],
          beyond: [],
          public_domain: [],
          did_you_mean: data.did_you_mean || [],
          forgave: Boolean(data.forgave),
          beyond_error: "",
          beyond_disclosure: data.beyond_disclosure || {},
        });
        if (!keeper) {
          setPhase("done");
          return;
        }
        setPhase("beyond");
        return api.searchBeyond(searchRequestQuery(bag), extras).then(
          (beyond) => {
            if (!alive) return;
            setResult((prev) => ({
              ...prev,
              beyond: beyond.beyond || [],
              public_domain: beyond.public_domain || [],
              beyond_error: beyond.beyond_error || "",
            }));
            setPhase("done");
          },
          (err) => {
            if (!alive) return;
            setResult((prev) => ({ ...prev, beyond_error: humanError(err) }));
            setPhase("done");
          },
        );
      })
      .catch((err) => {
        if (!alive) return;
        setError(humanError(err));
        setPhase("error");
      });
    return () => {
      alive = false;
    };
  }, [composed, fields.q, fields.kind, mode, fields.author, fields.title, fields.isbn, fields.series, fields.year, fields.issue, fields.artist, fields.album, keeper]);

  useEffect(() => {
    if (!discoverOpen) return undefined;
    let alive = true;
    setDiscoverPhase("loading");
    setDiscoverError("");
    const extras = discoverFeedRequest(discoverPage);
    api
      .discover(extras)
      .then((data) => {
        if (!alive) return;
        setDiscover({
          items: data.items || [],
          categories: data.categories || [],
          limit: data.limit || extras.limit,
          offset: data.offset || extras.offset || 0,
        });
        if (data.beyond_error) {
          setDiscoverError(humanError(data.beyond_error));
          setDiscoverPhase((data.items || []).length ? "done" : "error");
        } else {
          setDiscoverPhase("done");
        }
        setDiscoverPaging("");
      })
      .catch((err) => {
        if (!alive) return;
        setDiscoverError(humanError(err));
        setDiscoverPhase("error");
        setDiscoverPaging("");
      });
    return () => {
      alive = false;
    };
  }, [discoverOpen, discoverPage]);

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
    const query = buildFindSearchParams(next);
    if (draft.trim() || composed) {
      if (mode) query.set("mode", mode);
    }
    setParams(query);
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

  async function fileAsk() {
    setAskBusy(true);
    setError("");
    try {
      const data = await api.askHouse({
        q: searchRequestQuery(fields),
        kind: fields.kind || "book",
        title: fields.title || fields.q,
        author: fields.author,
        isbn: fields.isbn,
      });
      setAsked("asked");
      setAskOpen(false);
    } catch (err) {
      setError(humanError(err));
      setAskOpen(false);
    } finally {
      setAskBusy(false);
    }
  }

  function onAskHouse() {
    if (readerSawDisclosure()) {
      fileAsk();
      return;
    }
    setAskOpen(true);
  }

  function confirmAsk() {
    rememberDisclosure();
    fileAsk();
  }

  const status = searchStatusLine({
    q: searchRequestQuery(fields),
    kind: composed ? fields.kind : kind,
    localCount: result.local?.length || 0,
    phase,
  });
  const suggestions = didYouMeanList(result);
  const forgiveNote = didYouMeanPresence(suggestions);
  const counts = countSearchFacets(result);
  const filtered = applySearchFacets(result, facet);
  const yearEntries = yearFacetEntries(counts.years);
  const yearOptions = yearEntries.map(([year]) => [year, year]);
  const yearCounts = Object.fromEntries(yearEntries);
  const beyondItems = (filtered.beyond || []).map((item) => ({
    ...item,
    job_status: jobs[item.guid || item.title] === "asked" ? "asked" : item.job_status,
    wanted:
      jobs[item.guid || item.title] === "saved"
        ? { id: "saved", status: "wanted" }
        : item.wanted,
  }));
  const beyondCopy = beyondSearchCopy({
    q: composed,
    error: result.beyond_error,
    role: user?.role,
  });
  const discoverItems = (discover.items || []).map((item) => ({
    ...item,
    job_status: jobs[item.guid || item.title] === "asked" ? "asked" : item.job_status,
    wanted:
      jobs[item.guid || item.title] === "saved"
        ? { id: "saved", status: "wanted" }
        : item.wanted,
  }));
  const discoverEmpty = discoverStatusLine({
    phase: discoverPhase === "loading" ? "loading" : discoverPhase === "error" ? "error" : "done",
    count: discoverItems.length,
  });

  function toggleDiscover() {
    if (discoverOpen) {
      setDiscoverOpen(false);
      setDiscoverPage(0);
      setDiscoverPaging("");
      return;
    }
    setDiscoverPage(0);
    setDiscoverPaging("");
    setDiscoverPhase("loading");
    setDiscoverError("");
    setDiscover({ items: [], categories: [], limit: DISCOVER_PAGE_SIZE, offset: 0 });
    setDiscoverOpen(true);
  }

  function goDiscoverPage(nextPage) {
    const page = Math.max(0, nextPage);
    setDiscoverPaging(page > discoverPage ? "next" : "prev");
    setDiscoverPage(page);
    setDiscoverPhase("loading");
    setDiscoverError("");
    setDiscover((prev) => ({ ...prev, items: [] }));
  }

  function onDiscoverFold(event) {
    const open = event.currentTarget.open;
    if (!open) {
      setDiscoverOpen(false);
      setDiscoverPage(0);
      setDiscoverPaging("");
      return;
    }
    setDiscoverPage(0);
    setDiscoverPaging("");
    setDiscoverPhase("loading");
    setDiscoverError("");
    setDiscover({ items: [], categories: [], limit: DISCOVER_PAGE_SIZE, offset: 0 });
    setDiscoverOpen(true);
  }

  function renderDiscoverFeed() {
    return (
      <section
        id="discover-panel"
        className="discover-panel"
        data-testid="discover-panel"
        aria-busy={discoverPhase === "loading"}
      >
        <h2 className="sr-only">Discover</h2>
        {discoverError ? (
          <p className="callout" role="status" data-testid="discover-error">
            {discoverError}
          </p>
        ) : null}
        {discoverPhase === "loading" && !discoverItems.length ? <SkeletonRail label="Warming Discover…" /> : null}
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
        <div className="discover-pager">
          <ThinkingButton
            type="button"
            className="cta outline compact"
            onClick={() => goDiscoverPage(discoverPage - 1)}
            busy={discoverPaging === "prev"}
            disabled={discoverPage === 0 || discoverPhase === "loading"}
          >
            Previous
          </ThinkingButton>
          <ThinkingButton
            type="button"
            className="cta outline compact"
            onClick={() => goDiscoverPage(discoverPage + 1)}
            busy={discoverPaging === "next"}
            disabled={discoverItems.length < DISCOVER_PAGE_SIZE || discoverPhase === "loading"}
          >
            Next
          </ThinkingButton>
        </div>
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
          <p className="search-noted-door muted" data-testid="noted-door">
            <Link to="/noted">New & noted</Link>
          </p>
          {keeper ? (
            <>
              <div className="discover-launch">
                <button
                  type="button"
                  className="cta outline"
                  data-testid="discover-toggle"
                  aria-expanded={discoverOpen}
                  aria-controls="discover-panel"
                  onClick={toggleDiscover}
                >
                  Discover
                </button>
              </div>
              {discoverOpen ? renderDiscoverFeed() : null}
            </>
          ) : null}
        </>
      ) : (
        <div className="search-with-facets">
          <aside className="search-facets" aria-label="Filters">
            {fields.kind ? null : (
              <FacetGroup
                legend="Format"
                options={FORMAT_FACETS}
                value={facet.format}
                onChange={(format) => setFacet((prev) => ({ ...prev, format }))}
                counts={counts.formats}
              />
            )}
            <FacetGroup
              legend="Where"
              options={keeper ? WHERE_FACETS : WHERE_FACETS.filter(([key]) => key === "shelf")}
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
              empty={phase === "local" ? "Searching…" : localSearchEmpty(composed)}
              role={user?.role}
            />
            {keeper ? (
            <section id="beyond" className="search-beyond" data-testid="search-beyond">
              <h2>Beyond the shelves</h2>
              {result.beyond_error && beyondCopy.ownerDetail ? (
                <p className="alert" data-testid="search-beyond-error">
                  {beyondCopy.empty} {beyondCopy.ownerDetail}
                </p>
              ) : result.beyond_error ? (
                <p className="alert" data-testid="search-beyond-error">
                  {beyondCopy.empty}
                </p>
              ) : null}
              <Rail
                title="Beyond the shelves"
                kicker="NZBFinder and extra indexers"
                items={beyondItems}
                empty={
                  phase === "local" || phase === "beyond"
                    ? "Looking beyond the shelves…"
                    : beyondCopy.empty
                }
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
            ) : (
            <div className="search-ask-house" data-testid="search-ask-house">
              <p className="lede">{ASK_THE_HOUSE_PROMPT}</p>
              {asked ? (
                <p className="search-status" role="status">
                  The owner will look. Nothing downloads until they confirm.
                </p>
              ) : (
                <button type="button" className="cta" onClick={onAskHouse}>
                  {ASK_THE_HOUSE}
                </button>
              )}
            </div>
            )}
            {keeper ? (
            <details className="discover-fold" onToggle={onDiscoverFold}>
              <summary className="kicker">Discover</summary>
              {discoverOpen ? renderDiscoverFeed() : null}
            </details>
            ) : null}
          </div>
        </div>
      )}
      <ConfirmDialog
        open={askOpen}
        title={DISCLOSURE_TITLE}
        confirmLabel={ASK_THE_HOUSE}
        cancelLabel={DISCLOSURE_STAY}
        onConfirm={confirmAsk}
        onCancel={() => setAskOpen(false)}
        busy={askBusy}
        testId="search-ask-disclosure"
      >
        <p>{beyondDisclosureBody(result.beyond_disclosure || {})}</p>
      </ConfirmDialog>
    </div>
  );
}
