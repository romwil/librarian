import { useEffect, useState } from "react";
import { Link, useNavigate, useOutletContext } from "react-router-dom";
import { api } from "../api.js";
import Rail from "../components/Rail.jsx";

export default function HallPage() {
  const navigate = useNavigate();
  const { user } = useOutletContext();
  const [hall, setHall] = useState(null);
  const [q, setQ] = useState("");
  const owner = user?.role === "owner";

  useEffect(() => {
    api.hall().then(setHall).catch(() => setHall({ empty: true, areas: {} }));
  }, []);

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
      {hall?.empty ? (
        <section className="empty-cta">
          <h2>Open the stacks</h2>
          <p className="lede">Add an indexer and the first covers will land here.</p>
          {owner ? (
            <Link className="cta" to="/settings">
              Add an indexer
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
      <Rail title="Comics" items={hall?.areas?.comics} />
      <Rail title="Audiobooks" items={hall?.areas?.audiobooks} />
      <Rail title="Incoming Music" items={hall?.areas?.incoming_music} />
      <Rail title="Gaps" items={hall?.gaps} />
    </div>
  );
}
