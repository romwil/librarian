import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api } from "../api.js";
import Rail from "../components/Rail.jsx";

export default function SearchPage() {
  const [params, setParams] = useSearchParams();
  const q = params.get("q") || "";
  const [draft, setDraft] = useState(q);
  const [kind, setKind] = useState("");
  const [open, setOpen] = useState(false);
  const [result, setResult] = useState({ local: [], beyond: [] });
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
    await api.requestItem({
      title: item.title,
      guid: item.guid,
      kind: item.kind,
      download_url: item.download_url,
      author: item.author,
      isbn: item.isbn,
    });
  }

  return (
    <div className="hall">
      <section className="hero">
        <p className="eyebrow">Search</p>
        <form
          className="hero-search"
          onSubmit={(event) => {
            event.preventDefault();
            setParams({ q: draft });
          }}
        >
          <input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="In the stacks, then beyond" />
        </form>
        <button type="button" className="ghost" onClick={() => setOpen((v) => !v)}>
          Advanced
        </button>
        {open ? (
          <div className="drawer">
            <label>
              Kind
              <select value={kind} onChange={(e) => setKind(e.target.value)}>
                <option value="">Any</option>
                <option value="book">Book</option>
                <option value="magazine">Magazine</option>
                <option value="comic">Comic</option>
                <option value="audiobook">Audiobook</option>
                <option value="music">Music</option>
              </select>
            </label>
          </div>
        ) : null}
      </section>
      {error ? <p className="alert">{error}</p> : null}
      <Rail title="In the stacks" items={result.local} empty={q ? "Nothing on the shelves yet." : "Start typing."} />
      <Rail title="Beyond the shelves" items={result.beyond} onRequest={request} />
    </div>
  );
}
