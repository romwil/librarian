import { useEffect, useState } from "react";
import { Link, useNavigate, useOutletContext } from "react-router-dom";
import { api } from "../api.js";
import { browseHref, kindShelfTotalLine } from "../browse.js";
import Rail from "../components/Rail.jsx";
import TonightShelf from "../components/TonightShelf.jsx";
import CelebrationBanner from "../components/CelebrationBanner.jsx";
import { DISCOVER_CTA, emptyHallCopy, humanError, setupComplete } from "../copy.js";
import { bestsellersHref, discoverHref } from "../find.js";
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
  const counts = hall?.kind_counts || {};

  useEffect(() => {
    api
      .hall()
      .then((data) => {
        setHall(data);
        setLoadError("");
      })
      .catch((err) => {
        setHall({ empty: true, areas: {}, kind_counts: {} });
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
        <div className="hall-doors find-cta-block" data-testid="hall-doors">
          <Link className="cta outline" to={bestsellersHref()} data-testid="bestsellers-door">
            Bestsellers / curated lists
          </Link>
          <p className="muted">
            <Link className="muted" to={discoverHref()} data-testid="discover-door">
              {DISCOVER_CTA}
            </Link>
            {" · beyond the shelves without a search"}
          </p>
        </div>
      </section>
      {loadError ? <p className="alert hall-alert">{loadError}</p> : null}
      <CelebrationBanner items={hall?.celebrations || []} />
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
      <TonightShelf tonight={hall?.tonight} role={user?.role} />
      <Rail
        title="Continue listening"
        kicker="Pick up an audiobook where you left off"
        items={hall?.continue_listening}
        empty={hall ? "Start listening to leave a bookmark." : undefined}
      />
      <Rail
        title="Continue"
        kicker="In-progress reads"
        items={hall?.continue}
        empty={hall ? "Open a volume to leave a bookmark." : undefined}
      />
      <Rail title="What’s New" kicker="Recently organized" items={hall?.whats_new} />
      <Rail title="Favorites" items={hall?.favorites} seeAllTo={browseHref({ shelf: "favorites" })} />
      <Rail
        title="Books"
        kicker={kindShelfTotalLine("book", counts.book) || undefined}
        items={hall?.areas?.books}
        seeAllTo={browseHref({ kind: "book" })}
      />
      <Rail
        title="Magazines"
        kicker={kindShelfTotalLine("magazine", counts.magazine) || "Issue date on the gilt caption"}
        items={hall?.areas?.magazines}
        seeAllTo={browseHref({ kind: "magazine" })}
      />
      <Rail
        title="Comics"
        kicker={kindShelfTotalLine("comic", counts.comic) || "Series and issue, square-ish"}
        items={hall?.areas?.comics}
        seeAllTo={browseHref({ kind: "comic" })}
      />
      <Rail
        title="Audiobooks"
        kicker={kindShelfTotalLine("audiobook", counts.audiobook) || "Listen — not a book spine"}
        items={hall?.areas?.audiobooks}
        seeAllTo={browseHref({ kind: "audiobook" })}
      />
      <Rail
        title="Incoming Music"
        kicker={kindShelfTotalLine("music", counts.music) || "Promote lives in peek"}
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
