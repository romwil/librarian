import { useEffect, useState } from "react";
import { Link, useNavigate, useOutletContext } from "react-router-dom";
import { api } from "../api.js";
import { browseHref } from "../browse.js";
import QueryForm from "../components/QueryForm.jsx";
import Rail from "../components/Rail.jsx";
import WarmLoad from "../components/WarmLoad.jsx";
import { PAGE_TITLE_HALL, emptyHallCopy, humanError, setupComplete } from "../copy.js";
import useDocumentTitle from "../hooks/useDocumentTitle.js";
import { hallChipRow } from "../hallChips.js";
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

function HallRails({ owner, configured }) {
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
        setHall({ empty: true, kind_counts: {}, named_shelves: [] });
        setLoadError(humanError(err));
        setPhase("error");
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
  const chips = hallChipRow(hall || {});

  if (phase === "loading") {
    return <WarmLoad message="Warming the lamp on the Hall…" testId="hall-loading" />;
  }

  return (
    <div className="hall-shelves" data-testid="hall-shelves">
      {loadError ? <p className="alert hall-alert">{loadError}</p> : null}
      {chips.length ? (
        <nav className="chip-row hall-chips" aria-label="Shelves" data-testid="hall-chips">
          {chips.map((chip) => (
            <Link key={chip.key} className="chip" to={chip.href}>
              {chip.label}
              {chip.count ? ` · ${chip.count}` : ""}
            </Link>
          ))}
        </nav>
      ) : null}
      {hall?.empty ? (
        <section className="empty-cta hall-empty" data-testid="hall-empty">
          <h2>{empty.title}</h2>
          <p className="lede">{empty.lede}</p>
          {empty.cta && empty.href ? (
            <Link className="cta" to={empty.href}>
              {empty.cta}
            </Link>
          ) : null}
        </section>
      ) : null}
      {listening ? <Rail title="Continue listening" items={listening} cardMode="stacks" /> : null}
      {reading ? <Rail title="Continue reading" items={reading} cardMode="stacks" /> : null}
      {recent ? <Rail title="Recently added" items={recent} /> : null}
      {favorites ? (
        <Rail title="Favorites" items={favorites} seeAllTo={browseHref({ shelf: "favorites" })} />
      ) : null}
      <NotedRail items={noted} />
    </div>
  );
}

export default function HallPage() {
  const { user } = useOutletContext();
  const navigate = useNavigate();
  useDocumentTitle(PAGE_TITLE_HALL);
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
      <HallRails owner={owner} configured={configured} />
    </div>
  );
}
