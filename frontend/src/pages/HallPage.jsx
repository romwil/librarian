import { useEffect, useState } from "react";
import { Link, useNavigate, useOutletContext } from "react-router-dom";
import { api } from "../api.js";
import Rail from "../components/Rail.jsx";
import { emptyHallCopy, humanError, setupComplete } from "../copy.js";

export default function HallPage() {
  const navigate = useNavigate();
  const { user } = useOutletContext();
  const [hall, setHall] = useState(null);
  const [configured, setConfigured] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [q, setQ] = useState("");
  const owner = user?.role === "owner";
  const empty = emptyHallCopy({ owner, configured });

  useEffect(() => {
    api
      .hall()
      .then((data) => {
        setHall(data);
        setLoadError("");
      })
      .catch((err) => {
        setHall({ empty: true, areas: {} });
        setLoadError(humanError(err));
      });
    if (owner) {
      api
        .settings()
        .then((data) => setConfigured(setupComplete(data.settings)))
        .catch(() => setConfigured(false));
    }
  }, [owner]);

  function onSearch(event) {
    event.preventDefault();
    navigate(`/search?q=${encodeURIComponent(q)}`);
  }

  return (
    <div className="hall" data-testid="hall">
      <section className="hero-search-block">
        <p className="kicker">The Hall</p>
        <h1>What are you looking for?</h1>
        <p>One search. Shelves first, then the world.</p>
        <form className="search-field" onSubmit={onSearch}>
          <span aria-hidden="true">⌕</span>
          <label className="sr-only" htmlFor="hall-search">
            Search the stacks
          </label>
          <input
            id="hall-search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Author, title, ISBN, series…"
            autoFocus
          />
          <kbd>/</kbd>
        </form>
      </section>
      {loadError ? <p className="alert hall-alert">{loadError}</p> : null}
      {hall?.empty ? (
        <section className="empty-cta">
          <h2>{empty.title}</h2>
          <p className="lede">{empty.lede}</p>
          {owner ? (
            <Link className="cta" to="/settings">
              {configured ? "Open Settings" : "Add an indexer"}
            </Link>
          ) : null}
        </section>
      ) : null}
      <Rail
        title="Continue"
        kicker="In-progress reads and listens"
        items={hall?.continue}
        empty={hall ? "Open a volume to leave a bookmark." : undefined}
      />
      <Rail title="What’s New" kicker="Recently organized" items={hall?.whats_new} />
      <Rail title="Favorites" items={hall?.favorites} />
      <Rail title="Books" items={hall?.areas?.books} />
      <Rail title="Magazines" kicker="Issue date on the gilt caption" items={hall?.areas?.magazines} />
      <Rail title="Comics" kicker="Series and issue, square-ish" items={hall?.areas?.comics} />
      <Rail title="Audiobooks" kicker="Listen — not a book spine" items={hall?.areas?.audiobooks} />
      <Rail title="Incoming Music" kicker="Promote lives in peek" items={hall?.areas?.incoming_music} />
      <Rail title="Gaps" items={hall?.gaps} />
    </div>
  );
}
