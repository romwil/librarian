import { useEffect, useState } from "react";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import QueryForm from "../components/QueryForm.jsx";
import Rail from "../components/Rail.jsx";
import { FIND_BEYOND_CTA, FIELD_HELP, humanError, searchStatusLine } from "../copy.js";
import {
  buildFindSearchParams,
  composeSearchQuery,
  emptyFindFields,
  findFieldsFromSearchParams,
  findHref,
  pruneFieldsForKind,
} from "../find.js";

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
  const composed = composeSearchQuery(fields);
  const [draft, setDraft] = useState(fields.q);
  const [kind, setKind] = useState(fields.kind);
  const [advanced, setAdvanced] = useState(() => fieldsFromState(fields.q, fields.kind, fields));
  const [result, setResult] = useState({ local: [] });
  const [phase, setPhase] = useState("idle");
  const [error, setError] = useState("");

  useEffect(() => {
    const next = fieldsFromState(fields.q, fields.kind, fields);
    setDraft(next.q);
    setKind(next.kind);
    setAdvanced(next);
  }, [fields.q, fields.kind, fields.author, fields.title, fields.isbn, fields.series, fields.year, fields.issue, fields.artist, fields.album]);

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
      .search(composed, { beyond: false, kind: fields.kind })
      .then((data) => {
        if (!alive) return;
        setResult({ local: data.local || [] });
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
  }, [composed, fields.kind]);

  function commitSearch(nextKind = kind, nextAdvanced = advanced) {
    const next = fieldsFromState(draft, nextKind, nextAdvanced);
    setKind(next.kind);
    setAdvanced(next);
    setParams(Object.fromEntries(buildFindSearchParams(next)));
  }

  function onKindCommit(nextKind) {
    const next = fieldsFromState(draft, nextKind, advanced);
    setKind(next.kind);
    setAdvanced(next);
    if (draft.trim() || composed) {
      setParams(Object.fromEntries(buildFindSearchParams(next)));
    }
  }

  const status = searchStatusLine({
    q: composed,
    kind: composed ? fields.kind : kind,
    localCount: result.local?.length || 0,
    phase,
  });
  const showFindCta = Boolean(composed) && phase !== "idle" && phase !== "local";
  const ctaFields = fieldsFromState(draft.trim() || fields.q, kind, advanced);

  return (
    <div className="search-page">
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
      <p className="search-status" aria-live="polite" data-testid="search-status">
        {status}
      </p>
      {error ? (
        <p className="callout" role="status" data-testid="search-error">
          {error}
        </p>
      ) : null}
      {showFindCta ? (
        <div className="find-cta-block">
          <p className="kicker">Not on these shelves?</p>
          <Link className="cta" to={findHref(ctaFields)} data-testid="find-beyond-cta">
            {FIND_BEYOND_CTA}
          </Link>
        </div>
      ) : null}
      <Rail
        title="In the stacks"
        kicker={phase === "local" ? "Searching the shelves…" : "Local catalog · click cover to peek"}
        items={result.local}
        empty={composed ? (phase === "local" ? "Searching the shelves…" : "Nothing on the shelves yet.") : "Start typing."}
        role={user?.role}
      />
    </div>
  );
}
