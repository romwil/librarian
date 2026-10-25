import { useEffect, useState } from "react";
import { Link, useOutletContext } from "react-router-dom";
import { api } from "../api.js";
import { browseHref } from "../browse.js";
import Rail from "../components/Rail.jsx";
import { humanError } from "../copy.js";
import { continueRailItems } from "../hallRails.js";

export default function CardPage() {
  const { user } = useOutletContext();
  const [card, setCard] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    api
      .libraryCard()
      .then((data) => {
        if (cancelled) return;
        setCard(data);
        setError("");
      })
      .catch((err) => {
        if (!cancelled) setError(humanError(err));
      });
    return () => {
      cancelled = true;
    };
  }, [user?.id]);

  const reading = continueRailItems(card?.continue);
  const listening = continueRailItems(card?.continue_listening);
  const finished = continueRailItems(card?.finished);
  const favorites = continueRailItems(card?.favorites);
  const wantedCount = Number(card?.wanted_count || 0);

  return (
    <div className="hall page-settle" data-testid="library-card">
      <header className="browse-hero">
        <p className="kicker">Library card</p>
        <h1>Your library</h1>
      </header>
      {error ? <p className="alert">{error}</p> : null}
      {listening ? <Rail title="Continue listening" items={listening} role={user?.role} /> : null}
      {reading ? <Rail title="Continue reading" items={reading} role={user?.role} /> : null}
      {finished ? <Rail title="Recently finished" items={finished} role={user?.role} /> : null}
      {favorites ? (
        <Rail title="Favorites" items={favorites} seeAllTo={browseHref({ shelf: "favorites" })} role={user?.role} />
      ) : null}
      <p className="lede" style={{ padding: "0 var(--gutter)" }}>
        <Link to="/wanted">Wanted</Link>
        {wantedCount ? ` · ${wantedCount}` : ""}
      </p>
    </div>
  );
}
