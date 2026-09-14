import { useEffect, useState } from "react";
import { useOutletContext, useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import Rail from "../components/Rail.jsx";

const KINDS = [
  ["", "Any"],
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
  const [result, setResult] = useState({ local: [], beyond: [] });
  const [jobs, setJobs] = useState({});
  const [error, setError] = useState("");

  useEffect(() => {
    setDraft(q);
    if (!q.trim()) {
      setResult({ local: [], beyond: [] });
      return;
    }
    let alive = true;
    api
      .search(q, { beyond: false, kind })
      .then((data) => {
        if (alive) setResult(data);
      })
      .catch((err) => {
        if (alive) setError(err.message);
      });
    const timer = window.setTimeout(() => {
      api
        .search(q, { beyond: true, kind })
        .then((data) => {
          if (alive) setResult(data);
        })
        .catch(() => {});
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

  const beyond = (result.beyond || []).map((item) => ({
    ...item,
    job_status: jobs[item.guid || item.title],
  }));

  return (
    <div className="search-page">
      <form
        className="search-hero search-field"
        onSubmit={(event) => {
          event.preventDefault();
          setParams({ q: draft, ...(kind ? { kind } : {}) });
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
        {KINDS.filter(([value]) => value).map(([value, label]) => (
          <button
            key={value}
            type="button"
            className={`chip${kind === value ? " is-on" : ""}`}
            onClick={() => {
              const next = kind === value ? "" : value;
              setKind(next);
              if (draft.trim()) setParams({ q: draft, ...(next ? { kind: next } : {}) });
            }}
          >
            {label}
          </button>
        ))}
      </div>
      <details className="advanced">
        <summary className="kicker">Advanced — same page, not a different site</summary>
        <div className="field">
          <label htmlFor="adv-kind">Kind</label>
          <select id="adv-kind" value={kind} onChange={(e) => setKind(e.target.value)}>
            {KINDS.map(([value, label]) => (
              <option key={value || "any"} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
      </details>
      {error ? <p className="alert">{error}</p> : null}
      <Rail
        title="In the stacks"
        kicker="Local catalog · click cover to peek"
        items={result.local}
        empty={q ? "Nothing on the shelves yet." : "Start typing."}
        role={user?.role}
      />
      <Rail
        title="Beyond the shelves"
        kicker="NZBFinder · Request queues SAB. Readers file an asked slip."
        items={beyond}
        onRequest={request}
        beyond
        role={user?.role}
      />
    </div>
  );
}
