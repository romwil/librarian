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

  if (!items?.length) {
    return empty ? (
      <section className={`rail${beyond ? " beyond-rail" : ""}`}>
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
    <section className={`rail${beyond ? " beyond-rail" : ""}`}>
      <header className="rail-head">
        <div>
          <h2>{head}</h2>
          {kicker ? <p>{kicker}</p> : null}
        </div>
        {seeAll}
      </header>
      <div className="rail-track">
        {items.map((item) => (
          <CoverCard
            key={item.id || item.guid || item.title}
            work={item}
            onRequest={onRequest}
            beyond={beyond}
            role={role}
          />
        ))}
      </div>
    </section>
  );
}
