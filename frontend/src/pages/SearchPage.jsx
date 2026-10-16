import { useEffect, useState } from "react";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { kindCountFromFacets, kindShelfTotalLine } from "../browse.js";
import QueryForm from "../components/QueryForm.jsx";
import Rail from "../components/Rail.jsx";
import SearchModeControl, { normalizeSearchMode } from "../components/SearchModeControl.jsx";
import ShelfMore from "../components/ShelfMore.jsx";
import { DISCOVER_CTA, FIND_BEYOND_CTA, FIELD_HELP, humanError, searchStatusLine } from "../copy.js";
import {
  buildFindSearchParams,
  composeSearchQuery,
  discoverHref,
  emptyFindFields,
  findFieldsFromSearchParams,
  pruneFieldsForKind,
} from "../find.js";
import { didYouMeanList, didYouMeanPresence, searchForgave } from "../lib/searchForgive.js";

function fieldsFromState(draft, kind, advanced) {
  return pruneFieldsForKind(kind, {
    ...emptyFindFields(),
    ...advanced,
    q: draft,
    kind,
  });
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
  const [kindFacets, setKindFacets] = useState(null);

  useEffect(() => {
    const next = fieldsFromState(fields.q, fields.kind, fields);
    setDraft(next.q);
    setKind(next.kind);
    setAdvanced(next);
  }, [fields.q, fields.kind, fields.author, fields.title, fields.isbn, fields.series, fields.year, fields.issue, fields.artist, fields.album]);

  useEffect(() => {
    let alive = true;
    api
      .browseFacets()
      .then((data) => {
        if (alive) setKindFacets(data);
      })
      .catch(() => {
        if (alive) setKindFacets(null);
      });
    return () => {
      alive = false;
    };
  }, []);

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
  const activeKind = composed ? fields.kind : kind;
  const kindTotal = kindCountFromFacets(kindFacets, activeKind);
  const kindTotalLine = activeKind ? kindShelfTotalLine(activeKind, kindTotal) : "";
  const showFindCta = Boolean(composed) && phase !== "idle" && phase !== "local";
  const showDiscoverDoor = !composed;
  const ctaFields = fieldsFromState(draft.trim() || fields.q, kind, advanced);
  const suggestions = didYouMeanList(result);
  const forgiveNote = didYouMeanPresence(suggestions);

  return (
    <div className="search-page page-settle">
      <SearchModeControl mode={activeMode} onMode={onMode} />
      <QueryForm
        inputId="hall-search"
        draft={draft}
        onDraft={setDraft}
        kind={kind}
        onKindCommit={onKindCommit}
        advanced={advanced}
        onAdvanced={setAdvanced}
        onSubmit={() => commitSearch()}
        placeholder="In the stacks"
        ariaLabel="Search the stacks"
        kindHelp={FIELD_HELP.searchKind}
      />
      {kindTotalLine ? (
        <p className="kind-shelf-total muted" data-testid="kind-shelf-total">
          {kindTotalLine}
        </p>
      ) : null}
      <p className="search-status" aria-live="polite" data-testid="search-status">
        {status}
        {searchForgave(result) ? " · the lamp forgave a typo" : ""}
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
        title="In the stacks"
        kicker={phase === "local" ? "Searching the shelves…" : "Local catalog · click cover to peek"}
        items={result.local}
        empty={composed ? (phase === "local" ? "Searching the shelves…" : "Nothing on the shelves yet.") : "Start typing."}
        role={user?.role}
      />
      {composed && phase !== "idle" ? (
        <section id="beyond" className="search-beyond" data-testid="search-beyond">
          <h2>Beyond</h2>
          <Rail
            title="Usenet"
            kicker="NZBFinder and the extra indexers in Settings"
            items={result.beyond || []}
            empty={phase === "local" ? "Looking beyond the shelves…" : "Nothing on Usenet for this search."}
            beyond
            role={user?.role}
          />
          <div className="public-domain-lane" data-testid="public-domain-lane">
            <p className="kicker">Public domain</p>
            {(result.public_domain || []).length ? (
              <ul>
                {(result.public_domain || []).map((edition) => (
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
      ) : null}
      {showDiscoverDoor || showFindCta ? (
        <ShelfMore>
          {showDiscoverDoor ? (
            <p className="find-cta-block">
              <Link className="muted" to={discoverHref({ kind })} data-testid="discover-door">
                {DISCOVER_CTA}
              </Link>
            </p>
          ) : null}
          {showFindCta ? (
            <div className="find-cta-block">
              <p className="kicker">Not on these shelves?</p>
              <a className="cta" href="#beyond" data-testid="find-beyond-cta">
                {FIND_BEYOND_CTA}
              </a>
            </div>
          ) : null}
        </ShelfMore>
      ) : null}
    </div>
  );
}
