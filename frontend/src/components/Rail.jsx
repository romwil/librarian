import { Link } from "react-router-dom";
import CoverCard from "./CoverCard.jsx";

export default function Rail({
  title,
  kicker,
  items,
  empty,
  onRequest,
  beyond = false,
  role = "reader",
  seeAllTo = "",
  /** Continue / tonight presence — settle-in covers + lamp kicker chrome */
  presence = false,
}) {
  const head = seeAllTo ? (
    <Link to={seeAllTo} className="rail-title-link">
      {title}
    </Link>
  ) : (
    title
  );
  const seeAll = seeAllTo ? (
    <Link to={seeAllTo} className="rail-see-all" data-testid="rail-see-all">
      See all
    </Link>
  ) : null;
  const railClass = [
    "rail",
    beyond ? "beyond-rail" : "",
    presence ? "is-continue-presence" : "",
  ]
    .filter(Boolean)
    .join(" ");

  if (!items?.length) {
    return empty ? (
      <section className={railClass} data-presence={presence ? "lamp" : undefined}>
        <header className="rail-head">
          <div>
            <h2>{head}</h2>
            {kicker ? <p>{kicker}</p> : null}
          </div>
          {seeAll}
        </header>
        <p className="lede" style={{ padding: "0 var(--gutter)", color: "var(--muted)" }}>
          {empty}
        </p>
      </section>
    ) : null;
  }
  return (
    <section className={railClass} data-presence={presence ? "lamp" : undefined}>
      <header className="rail-head">
        <div>
          <h2>{head}</h2>
          {kicker ? <p>{kicker}</p> : null}
        </div>
        {seeAll}
      </header>
      <div className="rail-track">
        {items.map((item, index) => (
          <div
            key={item.id || item.guid || item.title}
            className={presence ? "cover-settle" : undefined}
            style={presence ? { "--settle-i": String(Math.min(index, 8)) } : undefined}
          >
            <CoverCard work={item} onRequest={onRequest} beyond={beyond} role={role} />
          </div>
        ))}
      </div>
    </section>
  );
}
