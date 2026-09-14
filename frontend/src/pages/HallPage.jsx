import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";
import Rail from "../components/Rail.jsx";

export default function HallPage() {
  const navigate = useNavigate();
  const [hall, setHall] = useState(null);
  const [q, setQ] = useState("");

  useEffect(() => {
    api.hall().then(setHall).catch(() => setHall({ empty: true, areas: {} }));
  }, []);

  function onSearch(event) {
    event.preventDefault();
    navigate(`/search?q=${encodeURIComponent(q)}`);
  }

  return (
    <div className="hall">
      <section className="hero">
        <p className="eyebrow">The Hall</p>
        <form className="hero-search" onSubmit={onSearch}>
          <label className="sr-only" htmlFor="hall-search">
            Search the stacks
          </label>
          <input
            id="hall-search"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search the stacks — then the world"
            autoFocus
          />
        </form>
      </section>
      {hall?.empty ? (
        <section className="empty-house">
          <h2>Open the stacks</h2>
          <p>Add an indexer in Settings and the first covers will land here.</p>
        </section>
      ) : null}
      <Rail title="What’s New" items={hall?.whats_new} />
      <Rail title="Favorites" items={hall?.favorites} />
      <Rail title="Books" items={hall?.areas?.books} />
      <Rail title="Magazines" items={hall?.areas?.magazines} />
      <Rail title="Comics" items={hall?.areas?.comics} />
      <Rail title="Audiobooks" items={hall?.areas?.audiobooks} />
      <Rail title="Incoming Music" items={hall?.areas?.incoming_music} />
      <Rail title="Gaps" items={hall?.gaps} empty={hall?.gaps ? undefined : undefined} />
    </div>
  );
}
