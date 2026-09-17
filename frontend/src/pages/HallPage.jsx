import { useEffect, useState } from "react";
import { Link, useNavigate, useOutletContext } from "react-router-dom";
import { api } from "../api.js";
import { browseHref } from "../browse.js";
import Rail from "../components/Rail.jsx";
import { DISCOVER_CTA, emptyHallCopy, humanError, setupComplete } from "../copy.js";
import { discoverHref } from "../find.js";
import AddToLibrary from "../components/AddToLibrary.jsx";

export default function HallPage() {
  const navigate = useNavigate();
  const { user } = useOutletContext();
  const [hall, setHall] = useState(null);
  const [configured, setConfigured] = useState(false);
  const [loadError, setLoadError] = useState("");
  const [q, setQ] = useState("");
  const owner = user?.role === "owner";
  const keeper = owner || user?.role === "op";
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
        <p>Search the stacks.</p>
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
        <p className="find-cta-block">
          <Link className="muted" to={discoverHref()} data-testid="discover-door">
            {DISCOVER_CTA}
          </Link>
        </p>
      </section>
      {loadError ? <p className="alert hall-alert">{loadError}</p> : null}
      {hall?.empty ? (
        <section className="empty-cta hall-empty" data-testid="hall-empty">
          <p className="empty-illustration" aria-hidden="true">
            <span className="empty-lamp" />
          </p>
          <h2>{empty.title}</h2>
          <p className="lede">{empty.lede}</p>
          {owner ? (
            <Link className="cta" to="/settings">
              {configured ? "Open Settings" : "Add an indexer"}
            </Link>
          ) : null}
        </section>
      ) : null}
      {keeper ? <AddToLibrary compact /> : null}
      <Rail
        title="Continue"
        kicker="In-progress reads and listens"
        items={hall?.continue}
        empty={hall ? "Open a volume to leave a bookmark." : undefined}
      />
      <Rail title="What’s New" kicker="Recently organized" items={hall?.whats_new} />
      <Rail title="Favorites" items={hall?.favorites} seeAllTo={browseHref({ shelf: "favorites" })} />
      <Rail title="Books" items={hall?.areas?.books} seeAllTo={browseHref({ kind: "book" })} />
      <Rail
        title="Magazines"
        kicker="Issue date on the gilt caption"
        items={hall?.areas?.magazines}
        seeAllTo={browseHref({ kind: "magazine" })}
      />
      <Rail
        title="Comics"
        kicker="Series and issue, square-ish"
        items={hall?.areas?.comics}
        seeAllTo={browseHref({ kind: "comic" })}
      />
      <Rail
        title="Audiobooks"
        kicker="Listen — not a book spine"
        items={hall?.areas?.audiobooks}
        seeAllTo={browseHref({ kind: "audiobook" })}
      />
      <Rail
        title="Incoming Music"
        kicker="Promote lives in peek"
        items={hall?.areas?.incoming_music}
        seeAllTo={browseHref({ kind: "music" })}
      />
      <Rail
        title="Gaps"
        kicker="Find this hole beyond the shelves"
        items={(hall?.gaps || []).map((item) => ({ ...item, gap: true }))}
      />
    </div>
  );
}
