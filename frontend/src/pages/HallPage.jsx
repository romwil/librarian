import { useEffect, useState } from "react";
import { Link, useNavigate, useOutletContext } from "react-router-dom";
import { api } from "../api.js";
import { browseHref, kindShelfTotalLine } from "../browse.js";
import Rail from "../components/Rail.jsx";
import TonightShelf from "../components/TonightShelf.jsx";
import { DISCOVER_CTA, emptyHallCopy, humanError, setupComplete } from "../copy.js";
import { discoverHref } from "../find.js";
import { hallLampPeriod, hallLampPeriodLabel, welcomeBackCopy } from "../lib/lampRituals.js";

/** Deferred shelves — hero paints first; this block loads with a clear warming state. */
function HallShelves({ role, owner, configured, lampPeriod }) {
  const [hall, setHall] = useState(null);
  const [phase, setPhase] = useState("loading");
  const [loadError, setLoadError] = useState("");
  const empty = emptyHallCopy({ owner, configured });
  const counts = hall?.kind_counts || {};
  const welcome =
    phase === "ready"
      ? welcomeBackCopy({
          continueCount: (hall?.continue || []).length,
          listeningCount: (hall?.continue_listening || []).length,
          period: lampPeriod,
        })
      : "";

  useEffect(() => {
    let cancelled = false;
    let timeoutId = 0;
    // Defer fetch so the search hero paints before rails work.
    const raf = window.requestAnimationFrame(() => {
      timeoutId = window.setTimeout(() => {
        api
          .hall()
          .then((data) => {
            if (cancelled) return;
            setHall(data);
            setLoadError("");
            setPhase("ready");
          })
          .catch((err) => {
            if (cancelled) return;
            setHall({ empty: true, areas: {}, kind_counts: {} });
            setLoadError(humanError(err));
            setPhase("error");
          });
      }, 0);
    });
    return () => {
      cancelled = true;
      window.cancelAnimationFrame(raf);
      window.clearTimeout(timeoutId);
    };
  }, []);

  if (phase === "loading") {
    return (
      <section className="hall-shelves-loading" data-testid="hall-shelves-loading" aria-busy="true">
        <p className="kicker">Tonight’s shelf</p>
        <p className="muted">Warming the lamp on the shelves below…</p>
        <div className="hall-shelves-skeleton" aria-hidden="true" />
      </section>
    );
  }

  return (
    <div className="hall-shelves" data-testid="hall-shelves">
      {welcome ? (
        <p className="hall-welcome-back" data-testid="hall-welcome-back">
          {welcome}
        </p>
      ) : null}
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
      <TonightShelf tonight={hall?.tonight} role={role} />
      <Rail
        title="Continue listening"
        kicker="Where you left the lamp"
        items={hall?.continue_listening}
        empty={hall ? "Start listening to leave a bookmark under the lamp." : undefined}
        presence
      />
      <Rail
        title="Continue"
        kicker="Volumes waiting under the lamp"
        items={hall?.continue}
        empty={hall ? "Open a volume to leave a bookmark under the lamp." : undefined}
        presence
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

export default function HallPage() {
  const navigate = useNavigate();
  const { user } = useOutletContext();
  const [configured, setConfigured] = useState(false);
  const [q, setQ] = useState("");
  const [lampPeriod] = useState(() => hallLampPeriod());
  const owner = user?.role === "owner";

  useEffect(() => {
    if (!owner) return undefined;
    let cancelled = false;
    api
      .settings()
      .then((data) => {
        if (!cancelled) setConfigured(setupComplete(data.settings));
      })
      .catch(() => {
        if (!cancelled) setConfigured(false);
      });
    return () => {
      cancelled = true;
    };
  }, [owner]);

  function onSearch(event) {
    event.preventDefault();
    navigate(`/search?q=${encodeURIComponent(q)}`);
  }

  return (
    <div
      className="hall hall-page page-settle hall-lamp-ritual"
      data-testid="hall"
      data-lamp-period={lampPeriod}
    >
      <span className="sr-only">{hallLampPeriodLabel(lampPeriod)}</span>
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
        <p className="find-cta-block hall-discover" data-testid="hall-discover">
          <Link className="muted" to={discoverHref()} data-testid="discover-door">
            {DISCOVER_CTA}
          </Link>
          {" · beyond the shelves without a search"}
        </p>
      </section>
      <HallShelves role={user?.role} owner={owner} configured={configured} lampPeriod={lampPeriod} />
    </div>
  );
}
