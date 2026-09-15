import { useEffect, useState } from "react";
import { useOutletContext, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import { FieldLabel } from "../components/FieldHelp.jsx";
import Rail from "../components/Rail.jsx";
import { FIELD_HELP, humanError, searchStatusLine } from "../copy.js";

const KINDS = [
  ["", "All"],
  ["book", "Book"],
  ["magazine", "Magazine"],
  ["comic", "Comic"],
  ["audiobook", "Audiobook"],
  ["music", "Music"],
];

export default function SearchPage() {
  const [params, setParams] = useSearchParams();
  const { user } = useOutletContext();
  const q = params.get("q") || "";
  const [draft, setDraft] = useState(q);
  const [kind, setKind] = useState(params.get("kind") || "");
  const [advanced, setAdvanced] = useState({ author: "", title: "", isbn: "", series: "", year: "" });
  const [result, setResult] = useState({ local: [], beyond: [] });
  const [jobs, setJobs] = useState({});
  const [phase, setPhase] = useState("idle");
  const [error, setError] = useState("");

  useEffect(() => {
    setDraft(q);
    if (!q.trim()) {
      setResult({ local: [], beyond: [] });
      setPhase("idle");
      setError("");
      return;
    }
    let alive = true;
    setPhase("local");
    setError("");
    api
      .search(q, { beyond: false, kind })
      .then((data) => {
        if (!alive) return;
        setResult(data);
        setPhase("beyond");
      })
      .catch((err) => {
        if (alive) {
          setError(humanError(err));
          setPhase("beyond_error");
        }
      });
    const timer = window.setTimeout(() => {
      api
        .search(q, { beyond: true, kind })
        .then((data) => {
          if (!alive) return;
          setResult(data);
          if (data.beyond_error) {
            setError(humanError(data.beyond_error));
            setPhase("beyond_error");
          } else {
            setError("");
            setPhase("done");
          }
        })
        .catch((err) => {
          if (alive) {
            setError(humanError(err));
            setPhase("beyond_error");
          }
        });
    }, 400);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [q, kind]);

  async function request(item) {
    const data = await api.requestItem({
      title: item.title,
      guid: item.guid,
      kind: item.kind,
      download_url: item.download_url,
      author: item.author,
      isbn: item.isbn,
    });
    const key = item.guid || item.title;
    setJobs((prev) => ({ ...prev, [key]: data.job?.status || "asked" }));
    return data;
  }

  function commitSearch(nextKind = kind) {
    const pieces = [draft, advanced.author, advanced.title, advanced.isbn, advanced.series, advanced.year]
      .map((value) => String(value || "").trim())
      .filter(Boolean);
    const nextQ = pieces.join(" ");
    setParams({ q: nextQ, ...(nextKind ? { kind: nextKind } : {}) });
  }

  const beyond = (result.beyond || []).map((item) => ({
    ...item,
    job_status: jobs[item.guid || item.title],
  }));
  const status = searchStatusLine({
    q,
    kind,
    localCount: result.local?.length || 0,
    beyondCount: beyond.length,
    phase,
  });
  const beyondEmpty =
    phase === "beyond"
      ? "Looking beyond the shelves…"
      : phase === "beyond_error"
        ? "Beyond the shelves is quiet. The note above explains why."
        : q
          ? "Nothing beyond the shelves yet."
          : "Start typing.";

  return (
    <div className="search-page">
      <form
        className="search-hero search-field"
        onSubmit={(event) => {
          event.preventDefault();
          commitSearch();
        }}
      >
        <span aria-hidden="true">⌕</span>
        <input
          id="hall-search"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder="In the stacks, then beyond"
          aria-label="Search"
        />
        <kbd>/</kbd>
      </form>
      <div className="search-hero chip-row" style={{ justifyContent: "center", marginBottom: 12 }}>
        {KINDS.map(([value, label]) => (
          <button
            key={value || "all"}
            type="button"
            className={`chip${kind === value ? " is-on" : ""}`}
            aria-pressed={kind === value}
            onClick={() => {
              const next = value;
              setKind(next);
              if (draft.trim() || q.trim()) commitSearch(next);
            }}
          >
            {label}
          </button>
        ))}
      </div>
      <p className="search-status" aria-live="polite" data-testid="search-status">
        {status}
      </p>
      <details className="advanced">
        <summary className="kicker">Advanced — same page, not a different site</summary>
        <div className="field">
          <FieldLabel htmlFor="adv-kind" label="Kind" help={FIELD_HELP.searchKind} />
          <select id="adv-kind" value={kind} onChange={(e) => setKind(e.target.value)}>
            {KINDS.map(([value, label]) => (
              <option key={value || "any"} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="field">
          <FieldLabel htmlFor="adv-author" label="Author" help={FIELD_HELP.searchAuthor} />
          <input
            id="adv-author"
            value={advanced.author}
            onChange={(e) => setAdvanced({ ...advanced, author: e.target.value })}
          />
        </div>
        <div className="field">
          <FieldLabel htmlFor="adv-title" label="Title" help={FIELD_HELP.searchTitle} />
          <input
            id="adv-title"
            value={advanced.title}
            onChange={(e) => setAdvanced({ ...advanced, title: e.target.value })}
          />
        </div>
        <div className="field">
          <FieldLabel htmlFor="adv-isbn" label="ISBN" help={FIELD_HELP.searchIsbn} />
          <input
            id="adv-isbn"
            className="font-mono"
            value={advanced.isbn}
            onChange={(e) => setAdvanced({ ...advanced, isbn: e.target.value })}
          />
        </div>
        <div className="field">
          <FieldLabel htmlFor="adv-series" label="Series" help={FIELD_HELP.searchSeries} />
          <input
            id="adv-series"
            value={advanced.series}
            onChange={(e) => setAdvanced({ ...advanced, series: e.target.value })}
          />
        </div>
        <div className="field">
          <FieldLabel htmlFor="adv-year" label="Year" help={FIELD_HELP.searchYear} />
          <input
            id="adv-year"
            value={advanced.year}
            onChange={(e) => setAdvanced({ ...advanced, year: e.target.value })}
          />
        </div>
      </details>
      {error ? (
        <p className="callout" role="status" data-testid="beyond-error">
          {error}
        </p>
      ) : null}
      <Rail
        title="In the stacks"
        kicker={phase === "local" ? "Searching the shelves…" : "Local catalog · click cover to peek"}
        items={result.local}
        empty={q ? (phase === "local" ? "Searching the shelves…" : "Nothing on the shelves yet.") : "Start typing."}
        role={user?.role}
      />
      <Rail
        title="Beyond the shelves"
        kicker="NZBFinder · Request queues SAB. Readers file an asked slip."
        items={beyond}
        empty={beyondEmpty}
        onRequest={request}
        beyond
        role={user?.role}
      />
    </div>
  );
}
