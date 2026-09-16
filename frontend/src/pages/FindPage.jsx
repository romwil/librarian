import { useEffect, useMemo, useState } from "react";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import QueryForm from "../components/QueryForm.jsx";
import Rail from "../components/Rail.jsx";
import RssPanel from "../components/RssPanel.jsx";
import { FIELD_HELP, discoverKindNote, discoverStatusLine, findStatusLine, humanError } from "../copy.js";
import {
  buildFindSearchParams,
  composeSearchQuery,
  emptyFindFields,
  findFieldsFromSearchParams,
  findKindOptions,
  hasFindQuery,
  pruneFieldsForKind,
  requestBodyFromHit,
  searchHref,
  shouldShowDiscover,
} from "../find.js";

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

export default function FindPage() {
  const [params, setParams] = useSearchParams();
  const { user, features } = useOutletContext();
  const showExtra = Boolean(features?.show_extra_categories);
  const kindOptions = findKindOptions(showExtra);
  const urlFields = pruneFieldsForKind(
    findFieldsFromSearchParams(params).kind,
    findFieldsFromSearchParams(params),
  );
  const composed = composeSearchQuery(urlFields);
  const [draft, setDraft] = useState(urlFields.q);
  const [kind, setKind] = useState(urlFields.kind);
  const [advanced, setAdvanced] = useState(urlFields);
  const [cat, setCat] = useState("");
  const [result, setResult] = useState({ beyond: [] });
  const [discover, setDiscover] = useState({ items: [], categories: [] });
  const [jobs, setJobs] = useState({});
  const [phase, setPhase] = useState("idle");
  const [discoverPhase, setDiscoverPhase] = useState("idle");
  const [error, setError] = useState("");
  const [discoverError, setDiscoverError] = useState("");
  const openDiscover = shouldShowDiscover(urlFields);

  useEffect(() => {
    setDraft(urlFields.q);
    setKind(urlFields.kind);
    setAdvanced(urlFields);
    setCat("");
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
    api
      .discover({ kind: urlFields.kind, cat })
      .then((data) => {
        if (!alive) return;
        setDiscover({ items: data.items || [], categories: data.categories || [] });
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
  }, [urlFields.kind, cat]);

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
    setCat("");
    if (hasFindQuery(next)) commitFind(nextKind, next);
    else setParams(nextKind ? { kind: nextKind } : {});
  }

  async function request(item) {
    const sought = fieldsFromState(draft, kind, advanced);
    const data = await api.requestItem(requestBodyFromHit(item, sought));
    const key = item.guid || item.title;
    setJobs((prev) => ({ ...prev, [key]: data.job?.status || "asked" }));
    return data;
  }

  const beyond = (result.beyond || []).map((item) => ({
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
    beyondCount: beyond.length,
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

  function renderDiscover() {
    return (
      <section className="discover-panel" data-testid="discover-panel">
        <header className="discover-head">
          <h2>Discover</h2>
          <p className="lede discover-lede">{discoverKindNote(urlFields.kind)}</p>
        </header>
        {kindCats.length > 1 ? (
          <div className="search-hero chip-row discover-cats">
            <button
              type="button"
              className={`chip${cat === "" ? " is-on" : ""}`}
              aria-pressed={cat === ""}
              onClick={() => setCat("")}
            >
              All
            </button>
            {kindCats.map((row) => (
              <button
                key={row.id}
                type="button"
                className={`chip${cat === String(row.id) ? " is-on" : ""}`}
                aria-pressed={cat === String(row.id)}
                onClick={() => setCat(String(row.id))}
              >
                {row.name}
              </button>
            ))}
          </div>
        ) : null}
        {discoverError ? (
          <p className="callout" role="status" data-testid="discover-error">
            {discoverError}
          </p>
        ) : null}
        {rails.length ? (
          rails.map((rail) => (
            <Rail
              key={rail.id}
              title={rail.title}
              kicker="Indexers · Request queues SAB. Readers file an asked slip."
              items={rail.items}
              onRequest={request}
              beyond
              role={user?.role}
            />
          ))
        ) : (
          <p className="lede discover-empty">{discoverEmpty}</p>
        )}
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
        <Rail
          title="Beyond the shelves"
          kicker="Indexers · Request queues SAB. Readers file an asked slip. Host names stay muted on the card."
          items={beyond}
          empty={beyondEmpty}
          onRequest={request}
          beyond
          role={user?.role}
        />
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
