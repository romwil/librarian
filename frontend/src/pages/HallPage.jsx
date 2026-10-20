import { useEffect, useState } from "react";
import { Link, useNavigate, useOutletContext } from "react-router-dom";
import { api } from "../api.js";
import HallCollection from "../components/HallCollection.jsx";
import QueryForm from "../components/QueryForm.jsx";
import Rail from "../components/Rail.jsx";
import SeriesCatchUp from "../components/SeriesCatchUp.jsx";
import TonightShelf from "../components/TonightShelf.jsx";
import { emptyHallCopy, humanError, setupComplete } from "../copy.js";
import { continueRailItems, notedRailItems } from "../hallRails.js";

function NotedRail({ items }) {
  if (!items?.length) return null;
  return (
    <section className="rail" data-testid="noted-rail">
      <header className="rail-head">
        <div>
          <h2>
            <Link to="/noted">New & noted</Link>
          </h2>
        </div>
      </header>
      <div className="rail-track">
        {items.map((item) => (
          <Link key={item.key} className="hall-noted-title" to={item.href}>
            <strong>{item.title}</strong>
            {item.author ? <em>{item.author}</em> : null}
          </Link>
        ))}
      </div>
    </section>
  );
}

function HallRails({ role, owner, configured }) {
  const [hall, setHall] = useState(null);
  const [phase, setPhase] = useState("loading");
  const [loadError, setLoadError] = useState("");
  const [noted, setNoted] = useState(null);
  const empty = emptyHallCopy({ owner, configured });

  useEffect(() => {
    let cancelled = false;
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
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (phase !== "ready" || !hall?.gaps_pending) return undefined;
    let cancelled = false;
    api
      .gapsLocal()
      .then((data) => {
        if (cancelled) return;
        setHall((prev) => {
          if (!prev) return prev;
          const nextGap = data?.tonight_gap ?? null;
          const tonight = prev.tonight
            ? {
                ...prev.tonight,
                gap: nextGap,
                empty: !(prev.tonight.continue || nextGap || prev.tonight.surprise),
              }
            : prev.tonight;
          return {
            ...prev,
            gaps: Array.isArray(data?.gaps) ? data.gaps : [],
            gaps_presence: data?.gaps_presence ?? prev.gaps_presence,
            series_catch_up: data?.series_catch_up ?? prev.series_catch_up,
            gaps_pending: false,
            tonight,
          };
        });
      })
      .catch(() => {
        if (!cancelled) {
          setHall((prev) => (prev ? { ...prev, gaps_pending: false } : prev));
        }
      });
    return () => {
      cancelled = true;
    };
  }, [phase, hall?.gaps_pending]);

  useEffect(() => {
    if (phase !== "ready") return undefined;
    let cancelled = false;
    api
      .noted()
      .then((data) => {
        if (!cancelled) setNoted(notedRailItems(data));
      })
      .catch(() => {
        if (!cancelled) setNoted(null);
      });
    return () => {
      cancelled = true;
    };
  }, [phase]);

  const reading = continueRailItems(hall?.continue);
  const listening = continueRailItems(hall?.continue_listening);
  const recent = continueRailItems(hall?.whats_new);
  const favorites = continueRailItems(hall?.favorites);

  return (
    <>
      {phase === "loading" ? null : (
        <div className="hall-shelves" data-testid="hall-shelves">
          {loadError ? <p className="alert hall-alert">{loadError}</p> : null}
          {hall?.empty ? (
            <section className="empty-cta hall-empty" data-testid="hall-empty">
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
          <SeriesCatchUp catchUp={hall?.series_catch_up} role={role} />
          {listening ? <Rail title="Continue listening" items={listening} /> : null}
          {reading ? <Rail title="Continue reading" items={reading} /> : null}
          {recent ? <Rail title="Recently added" items={recent} /> : null}
          {favorites ? (
            <Rail title="Favorites" items={favorites} seeAllTo="/?shelf=favorites" />
          ) : null}
          <NotedRail items={noted} />
        </div>
      )}
      <HallCollection role={role} favoritesAvailable={Boolean(favorites)} />
    </>
  );
}

export default function HallPage() {
  const { user } = useOutletContext();
  const navigate = useNavigate();
  const [configured, setConfigured] = useState(false);
  const [draft, setDraft] = useState("");
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

  return (
    <div className="hall hall-page page-settle" data-testid="hall">
      <header className="hero-search-block">
        <h1>Hall</h1>
        <QueryForm
          variant="hero"
          inputId="hall-search"
          draft={draft}
          onDraft={setDraft}
          onSubmit={() => {
            const q = draft.trim();
            navigate(q ? `/search?q=${encodeURIComponent(q)}` : "/search");
          }}
          placeholder="Title, author, or ISBN"
          ariaLabel="Search"
        />
      </header>
      <HallRails role={user?.role} owner={owner} configured={configured} />
    </div>
  );
}
