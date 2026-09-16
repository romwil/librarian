import { useEffect, useState } from "react";
import { Link, useOutletContext, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import QueryForm from "../components/QueryForm.jsx";
import Rail from "../components/Rail.jsx";
import { FIND_BEYOND_CTA, FIELD_HELP, humanError, searchStatusLine } from "../copy.js";
import { buildFindSearchParams, composeSearchQuery, findFieldsFromSearchParams, findHref } from "../find.js";

function fieldsFromState(draft, kind, advanced) {
  return {
    q: draft,
    kind,
    author: advanced.author,
    title: advanced.title,
    isbn: advanced.isbn,
    series: advanced.series,
    year: advanced.year,
    issue: advanced.issue,
    artist: advanced.artist,
    album: advanced.album,
  };
}

export default function SearchPage() {
  const [params, setParams] = useSearchParams();
  const { user } = useOutletContext();
  const fields = findFieldsFromSearchParams(params);
  const composed = composeSearchQuery(fields);
  const [draft, setDraft] = useState(fields.q);
  const [kind, setKind] = useState(fields.kind);
  const [advanced, setAdvanced] = useState({
    author: fields.author,
    title: fields.title,
    isbn: fields.isbn,
    series: fields.series,
    year: fields.year,
    issue: fields.issue,
    artist: fields.artist,
    album: fields.album,
  });
  const [result, setResult] = useState({ local: [] });
  const [phase, setPhase] = useState("idle");
  const [error, setError] = useState("");

  useEffect(() => {
    setDraft(fields.q);
    setKind(fields.kind);
    setAdvanced({
      author: fields.author,
      title: fields.title,
      isbn: fields.isbn,
      series: fields.series,
      year: fields.year,
      issue: fields.issue,
      artist: fields.artist,
      album: fields.album,
    });
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

  function commitSearch(nextKind = kind) {
    setKind(nextKind);
    setParams(Object.fromEntries(buildFindSearchParams(fieldsFromState(draft, nextKind, advanced))));
  }

  function onKindCommit(nextKind) {
    setKind(nextKind);
    if (draft.trim() || composed) commitSearch(nextKind);
  }

  const status = searchStatusLine({
    q: composed,
    kind: fields.kind,
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
