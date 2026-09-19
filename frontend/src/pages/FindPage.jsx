import { useEffect, useMemo, useState } from "react";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import QueryForm from "../components/QueryForm.jsx";
import Rail from "../components/Rail.jsx";
import RssPanel from "../components/RssPanel.jsx";
import CoverCard from "../components/CoverCard.jsx";
import BestsellersPanel from "../components/BestsellersPanel.jsx";
import { FIELD_HELP, discoverKindNote, discoverStatusLine, findStatusLine, humanError } from "../copy.js";
import PartSetCard from "../components/PartSetCard.jsx";
import {
  DISCOVER_BROWSE_LIMIT,
  bestsellersFromSearchParams,
  bestsellersHref,
  buildFindSearchParams,
  catalogGapFanoutQueries,
  composeSearchQuery,
  discoverCatFromSearchParams,
  discoverHref,
  emptyFindFields,
  findFieldsFromSearchParams,
  findKindOptions,
  groupDiscoverCategories,
  hasFindQuery,
  isCatalogGapQuery,
  pruneFieldsForKind,
  rankBeyondByCompleteness,
  requestBodyFromHit,
  searchHref,
  shouldShowDiscover,
} from "../find.js";
import {
  GAP_CHASE_QUERY_CAP,
  annotateChasedGaps,
  buildGapChaseQueries,
  groupBeyondItems,
  mergeBeyondHits,
} from "../findParts.js";

function fieldsFromState(draft, kind, advanced) {
  return pruneFieldsForKind(kind, {
    ...emptyFindFields(),
    ...advanced,
    q: draft,
    kind,
  });
}

function groupDiscoverRails(items, categories) {
  const labels = new Map((categories || []).map((row) => [String(row.id), row.name || row.id]));
  const groups = [];
  const index = new Map();
  for (const item of items || []) {
    const cat = item.category != null && item.category !== "" ? String(item.category) : "feed";
    const title = item.category_name || labels.get(cat) || cat;
    if (!index.has(cat)) {
      index.set(cat, groups.length);
      groups.push({ id: cat, title, items: [] });
    }
    groups[index.get(cat)].items.push(item);
  }
  return groups;
}

function discoverParams(kind, discoverCat) {
  const next = {};
  if (kind) next.kind = kind;
  if (discoverCat) next.discover = discoverCat;
  return next;
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

export default function FindPage() {
  const [params, setParams] = useSearchParams();
  const { user, features } = useOutletContext();
  const showExtra = Boolean(features?.show_extra_categories);
  const kindOptions = findKindOptions(showExtra);
  const urlFields = pruneFieldsForKind(
    findFieldsFromSearchParams(params).kind,
    findFieldsFromSearchParams(params),
  );
  const discoverCat = discoverCatFromSearchParams(params);
  const nytPreset = bestsellersFromSearchParams(params);
  const composed = composeSearchQuery(urlFields);
  const [draft, setDraft] = useState(urlFields.q);
  const [kind, setKind] = useState(urlFields.kind);
  const [advanced, setAdvanced] = useState(urlFields);
  const [result, setResult] = useState({ beyond: [] });
  const [chaseHits, setChaseHits] = useState([]);
  const [chaseBySet, setChaseBySet] = useState({});
  const [priorMissing, setPriorMissing] = useState({});
  const [bestMatches, setBestMatches] = useState([]);
  const [fanoutPhase, setFanoutPhase] = useState("idle");
  const [discover, setDiscover] = useState({ items: [], categories: [], limit: 0 });
  const [jobs, setJobs] = useState({});
  const [phase, setPhase] = useState("idle");
  const [discoverPhase, setDiscoverPhase] = useState("idle");
  const [error, setError] = useState("");
  const [discoverError, setDiscoverError] = useState("");
  const openDiscover = shouldShowDiscover(urlFields);
  const browsing = Boolean(discoverCat) && openDiscover;
  const catalogGap = isCatalogGapQuery(urlFields);

  useEffect(() => {
    setDraft(urlFields.q);
    setKind(urlFields.kind);
    setAdvanced(urlFields);
  }, [
    urlFields.q,
    urlFields.kind,
    urlFields.author,
    urlFields.title,
    urlFields.isbn,
    urlFields.series,
    urlFields.issue,
    urlFields.artist,
    urlFields.album,
    urlFields.year,
  ]);

  useEffect(() => {
    if (!hasFindQuery(urlFields)) {
      setResult({ beyond: [] });
      setChaseHits([]);
      setChaseBySet({});
      setPriorMissing({});
      setBestMatches([]);
      setFanoutPhase("idle");
      setPhase("idle");
      setError("");
      return undefined;
    }
    let alive = true;
    setPhase("beyond");
    setError("");
    setChaseHits([]);
    setChaseBySet({});
    setPriorMissing({});
    setBestMatches([]);
    setFanoutPhase("idle");
    api
      .search(urlFields.q, { beyond: true, ...urlFields })
      .then((data) => {
        if (!alive) return;
        setResult({ beyond: data.beyond || [] });
        if (data.beyond_error) {
          setError(humanError(data.beyond_error));
          setPhase((data.beyond || []).length ? "done" : "beyond_error");
        } else {
          setError("");
          setPhase("done");
        }
      })
      .catch((err) => {
        if (!alive) return;
        setError(humanError(err));
        setPhase("beyond_error");
      });
    return () => {
      alive = false;
    };
  }, [
    urlFields.q,
    urlFields.kind,
    urlFields.author,
    urlFields.title,
    urlFields.isbn,
    urlFields.series,
    urlFields.issue,
    urlFields.artist,
    urlFields.album,
    urlFields.year,
  ]);

  // B1 — multipart gap chase after primary beyond results land.
  useEffect(() => {
    if (phase !== "done") return undefined;
    const primary = groupBeyondItems(result.beyond || []);
    const incomplete = primary.sets.filter((set) => !set.complete && (set.missing || []).length);
    if (!incomplete.length) return undefined;

    let alive = true;
    const prior = {};
    for (const set of incomplete) prior[set.id] = [...(set.missing || [])];
    setPriorMissing(prior);

    (async () => {
      let budget = GAP_CHASE_QUERY_CAP;
      const extras = [];
      for (const set of incomplete) {
        if (!alive || budget <= 0) break;
        const queries = buildGapChaseQueries(set, { cap: budget });
        if (!queries.length) continue;
        setChaseBySet((prev) => ({
          ...prev,
          [set.id]: { status: "searching", queriesTried: 0, total: queries.length },
        }));
        let tried = 0;
        for (const q of queries) {
          if (!alive || budget <= 0) break;
          tried += 1;
          budget -= 1;
          setChaseBySet((prev) => ({
            ...prev,
            [set.id]: { status: "searching", queriesTried: tried, total: queries.length },
          }));
          try {
            const data = await api.search(q, { beyond: true, kind: set.kind || urlFields.kind });
            extras.push(...(data.beyond || []));
            if (alive) setChaseHits([...extras]);
          } catch {
            /* keep chasing */
          }
        }
        if (alive) {
          setChaseBySet((prev) => ({
            ...prev,
            [set.id]: { status: "done", queriesTried: tried, total: queries.length },
          }));
        }
      }
    })();

    return () => {
      alive = false;
    };
  }, [phase, result.beyond, urlFields.kind]);

  // B2 — catalog gap fan-out / Best matches (Confirm still required).
  useEffect(() => {
    if (phase !== "done" || !catalogGap) {
      setBestMatches([]);
      setFanoutPhase("idle");
      return undefined;
    }
    const queries = catalogGapFanoutQueries(urlFields, { cap: 5 }).slice(1);
    if (!queries.length) return undefined;
    let alive = true;
    setFanoutPhase("searching");
    (async () => {
      const extras = [];
      for (const fields of queries) {
        if (!alive) return;
        try {
          const data = await api.search(fields.q, { beyond: true, ...fields });
          extras.push(...(data.beyond || []));
        } catch {
          /* continue */
        }
      }
      if (!alive) return;
      const merged = mergeBeyondHits(result.beyond || [], extras).items;
      const { sets, singles } = groupBeyondItems(merged);
      const ranked = rankBeyondByCompleteness([
        ...sets.map((set) => ({ ...set, _rankType: "set" })),
        ...singles.map((item) => ({ ...item, _rankType: "single", found: 1, total: 1 })),
      ]).slice(0, 8);
      setBestMatches(ranked);
      setFanoutPhase("done");
    })();
    return () => {
      alive = false;
    };
  }, [phase, catalogGap, result.beyond, urlFields]);

  useEffect(() => {
    let alive = true;
    setDiscoverPhase("loading");
    setDiscoverError("");
    const extras = { kind: urlFields.kind, cat: discoverCat };
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
  }, [urlFields.kind, discoverCat]);

  function commitFind(nextKind = kind, nextAdvanced = advanced, nextDraft = draft) {
    const next = fieldsFromState(nextDraft, nextKind, nextAdvanced);
    setKind(next.kind);
    setAdvanced(next);
    setParams(Object.fromEntries(buildFindSearchParams(next, { prune: true })));
  }

  function onKindCommit(nextKind) {
    const next = fieldsFromState(draft, nextKind, advanced);
    setKind(nextKind);
    setAdvanced(next);
    if (hasFindQuery(next)) commitFind(nextKind, next);
    else setParams(discoverParams(nextKind, ""));
  }

  async function request(item) {
    const sought = fieldsFromState(draft, kind, advanced);
    const data = await api.requestItem(requestBodyFromHit(item, sought));
    const key = item.guid || item.title;
    setJobs((prev) => ({ ...prev, [key]: data.job?.status || "asked" }));
    return data;
  }

  const mergedBeyond = useMemo(
    () => mergeBeyondHits(result.beyond || [], chaseHits).items,
    [result.beyond, chaseHits],
  );
  const { sets: rawPartSets, singles: beyondSinglesRaw } = useMemo(
    () => groupBeyondItems(mergedBeyond),
    [mergedBeyond],
  );
  const partSets = useMemo(
    () =>
      rawPartSets.map((set) => {
        const chased = annotateChasedGaps(set, priorMissing[set.id] || []);
        const chaseMeta = chaseBySet[set.id];
        return {
          ...chased,
          chaseQueriesTried: chaseMeta?.queriesTried || 0,
        };
      }),
    [rawPartSets, priorMissing, chaseBySet],
  );
  const beyondSingles = beyondSinglesRaw.map((item) => ({
    ...item,
    job_status: jobs[item.guid || item.title],
  }));
  const discoverItems = (discover.items || []).map((item) => ({
    ...item,
    job_status: jobs[item.guid || item.title],
  }));
  const status = findStatusLine({
    q: composed,
    kind: urlFields.kind,
    beyondCount: mergedBeyond.length,
    phase,
  });
  const beyondEmpty =
    phase === "beyond"
      ? "Looking beyond the shelves…"
      : phase === "beyond_error"
        ? "Beyond the shelves is quiet. The note above explains why."
        : "Nothing beyond the shelves yet.";
  const discoverEmpty = discoverStatusLine({
    kind: urlFields.kind,
    phase: discoverPhase === "loading" ? "loading" : discoverPhase === "error" ? "error" : "done",
    count: discoverItems.length,
  });
  const kindCats = useMemo(
    () => (discover.categories || []).filter((row) => !urlFields.kind || row.kind === urlFields.kind),
    [discover.categories, urlFields.kind],
  );
  const rails = groupDiscoverRails(discoverItems, discover.categories);
  const browseTitle =
    kindCats.find((row) => String(row.id) === String(discoverCat))?.name ||
    discoverItems[0]?.category_name ||
    discoverCat;
  const backDiscoverHref = discoverHref({ kind: urlFields.kind });
  const anyChasing = Object.values(chaseBySet).some((row) => row?.status === "searching");

  function renderDiscoverBrowse() {
    return (
      <section className="discover-browse" data-testid="discover-browse">
        <header className="discover-browse-head">
          <Link className="discover-back" to={backDiscoverHref}>
            ← Discover
          </Link>
          <h2>{browseTitle || "Category"}</h2>
          <p>Indexers · Request queues SAB. Readers file an asked slip.</p>
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
        (discover.categories || []).find((row) => String(row.id) === String(rail.id))?.kind || urlFields.kind;
      return (
        <Rail
          key={rail.id}
          title={rail.title}
          kicker="Indexers · Request queues SAB. Readers file an asked slip."
          items={rail.items}
          onRequest={request}
          beyond
          role={user?.role}
          seeAllTo={discoverHref({ discover: rail.id, kind: feedKind || urlFields.kind })}
        />
      );
    });
  }

  function renderDiscover() {
    return (
      <section className="discover-panel" data-testid="discover-panel">
        <header className="discover-head">
          <h2>Discover</h2>
          <p className="lede discover-lede">{discoverKindNote(urlFields.kind)}</p>
        </header>
        {kindCats.length > 1 ? (
          <div className="discover-cats" data-testid="discover-cats">
            <div className="search-hero chip-row discover-cats-all">
              <button
                type="button"
                className={`chip${discoverCat === "" ? " is-on" : ""}`}
                aria-pressed={discoverCat === ""}
                onClick={() => setParams(discoverParams(urlFields.kind, ""))}
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
                      onClick={() => setParams(discoverParams(urlFields.kind || row.kind, String(row.id)))}
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

  function renderBestMatches() {
    if (!catalogGap || (!bestMatches.length && fanoutPhase !== "searching")) return null;
    return (
      <section className="best-matches" data-testid="best-matches">
        <header className="rail-head">
          <div>
            <h2>Best matches</h2>
            <p>Ranked by how complete the release looks. Request still files a slip — nothing auto-queues.</p>
          </div>
        </header>
        {fanoutPhase === "searching" && !bestMatches.length ? (
          <p className="lede" role="status">
            Checking other phrasings across the indexers…
          </p>
        ) : null}
        <div className="best-matches-strip">
          {bestMatches.map((row) => {
            if (row._rankType === "set" || row.parts) {
              return (
                <PartSetCard
                  key={`best-${row.id}`}
                  set={row}
                  onRequest={request}
                  role={user?.role}
                  jobs={jobs}
                  chase={chaseBySet[row.id]}
                />
              );
            }
            return (
              <CoverCard
                key={row.guid || row.title}
                work={{ ...row, job_status: jobs[row.guid || row.title] }}
                onRequest={request}
                beyond
                role={user?.role}
              />
            );
          })}
        </div>
      </section>
    );
  }

  return (
    <div className="search-page">
      <QueryForm
        inputId="find-search"
        draft={draft}
        onDraft={setDraft}
        kind={kind}
        onKindCommit={onKindCommit}
        advanced={advanced}
        onAdvanced={setAdvanced}
        onSubmit={() => commitFind()}
        placeholder="Beyond the shelves"
        ariaLabel="Find beyond the shelves"
        kindHelp={FIELD_HELP.findKind}
        variant="find"
        kinds={kindOptions}
      />
      <p className="search-status" aria-live="polite" data-testid="find-status">
        {status}
      </p>
      <p className="sr-only" role="status" aria-live="polite" data-testid="chase-live-region">
        {anyChasing ? "Searching for missing parts…" : ""}
      </p>
      {composed ? (
        <p className="find-cta-block">
          <Link className="muted" to={searchHref(fieldsFromState(draft.trim() || urlFields.q, kind, advanced))}>
            Search the stacks instead
          </Link>
        </p>
      ) : (
        <p className="find-cta-block">
          <Link className="muted" to={bestsellersHref()} data-testid="bestsellers-door">
            Bestsellers / curated lists
          </Link>
        </p>
      )}
      {nytPreset ? <BestsellersPanel list={nytPreset.list} date={nytPreset.date} /> : null}
      {error ? (
        <p className="callout" role="status" data-testid="beyond-error">
          {error}
        </p>
      ) : null}
      {composed ? (
        <>
          {phase === "beyond" && !partSets.length && !beyondSingles.length ? (
            <SkeletonRail label="Looking beyond the shelves…" />
          ) : null}
          {renderBestMatches()}
          {partSets.length ? (
            <section className="part-sets" data-testid="part-sets">
              <header className="rail-head">
                <div>
                  <h2>Multipart releases</h2>
                  <p>
                    Grouped from part / CD / disc markers. Select what you need — each Request files its own slip.
                    Incomplete sets chase missing parts quietly.
                  </p>
                </div>
              </header>
              {partSets.map((set) => (
                <PartSetCard
                  key={set.id}
                  set={set}
                  onRequest={request}
                  role={user?.role}
                  jobs={jobs}
                  chase={chaseBySet[set.id]}
                />
              ))}
            </section>
          ) : null}
          <Rail
            title={partSets.length ? "Other results" : "Beyond the shelves"}
            kicker="Indexers · Request queues SAB. Readers file an asked slip. Host names stay muted on the card."
            items={beyondSingles}
            empty={partSets.length ? "" : beyondEmpty}
            onRequest={request}
            beyond
            role={user?.role}
          />
        </>
      ) : null}
      {openDiscover ? (
        renderDiscover()
      ) : (
        <details className="discover-fold">
          <summary className="kicker">Discover — trending on the indexers</summary>
          {renderDiscover()}
        </details>
      )}
      {user?.role === "owner" || user?.role === "op" ? (
        <details className="more-settings find-rss">
          <summary className="kicker">RSS subscriptions</summary>
          <RssPanel compact />
        </details>
      ) : null}
    </div>
  );
}
