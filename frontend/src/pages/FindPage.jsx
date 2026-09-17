import { useEffect, useMemo, useState } from "react";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import QueryForm from "../components/QueryForm.jsx";
import Rail from "../components/Rail.jsx";
import RssPanel from "../components/RssPanel.jsx";
import CoverCard from "../components/CoverCard.jsx";
import { FIELD_HELP, discoverKindNote, discoverStatusLine, findStatusLine, humanError } from "../copy.js";
import PartSetCard from "../components/PartSetCard.jsx";
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
  hasFindQuery,
  pruneFieldsForKind,
  requestBodyFromHit,
  searchHref,
  shouldShowDiscover,
} from "../find.js";
import { groupBeyondItems } from "../findParts.js";

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
  const composed = composeSearchQuery(urlFields);
  const [draft, setDraft] = useState(urlFields.q);
  const [kind, setKind] = useState(urlFields.kind);
  const [advanced, setAdvanced] = useState(urlFields);
  const [result, setResult] = useState({ beyond: [] });
  const [discover, setDiscover] = useState({ items: [], categories: [], limit: 0 });
  const [jobs, setJobs] = useState({});
  const [phase, setPhase] = useState("idle");
  const [discoverPhase, setDiscoverPhase] = useState("idle");
  const [error, setError] = useState("");
  const [discoverError, setDiscoverError] = useState("");
  const openDiscover = shouldShowDiscover(urlFields);
  const browsing = Boolean(discoverCat) && openDiscover;

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
      setPhase("idle");
      setError("");
      return undefined;
    }
    let alive = true;
    setPhase("beyond");
    setError("");
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

  const { sets: partSets, singles: beyondSinglesRaw } = useMemo(
    () => groupBeyondItems(result.beyond || []),
    [result.beyond],
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
    beyondCount: (result.beyond || []).length,
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
    () =>
      (discover.categories || []).filter((row) => !urlFields.kind || row.kind === urlFields.kind),
    [discover.categories, urlFields.kind],
  );
  const rails = groupDiscoverRails(discoverItems, discover.categories);
  const browseTitle =
    kindCats.find((row) => String(row.id) === String(discoverCat))?.name ||
    discoverItems[0]?.category_name ||
    discoverCat;
  const backDiscoverHref = discoverHref({ kind: urlFields.kind });

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
          <p className="lede discover-empty">{discoverEmpty}</p>
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
    if (!rails.length) {
      return <p className="lede discover-empty">{discoverEmpty}</p>;
    }
    return rails.map((rail) => {
      const feedKind =
        (discover.categories || []).find((row) => String(row.id) === String(rail.id))?.kind ||
        urlFields.kind;
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
      {composed ? (
        <p className="find-cta-block">
          <Link className="muted" to={searchHref(fieldsFromState(draft.trim() || urlFields.q, kind, advanced))}>
            Search the stacks instead
          </Link>
        </p>
      ) : null}
      {error ? (
        <p className="callout" role="status" data-testid="beyond-error">
          {error}
        </p>
      ) : null}
      {composed ? (
        <>
          {partSets.length ? (
            <section className="part-sets" data-testid="part-sets">
              <header className="rail-head">
                <div>
                  <h2>Multipart releases</h2>
                  <p>
                    Grouped from part / CD / disc markers. Select what you need — each Request files its own slip.
                    Incomplete sets stay honest about missing parts.
                  </p>
                </div>
              </header>
              {partSets.map((set) => (
                <PartSetCard key={set.id} set={set} onRequest={request} role={user?.role} jobs={jobs} />
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
      {openDiscover ? renderDiscover() : (
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
