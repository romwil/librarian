import CoverCard from "./CoverCard.jsx";

export default function Rail({ title, kicker, items, empty, onRequest, beyond = false, role = "reader" }) {
  if (!items?.length) {
    return empty ? (
      <section className={`rail${beyond ? " beyond-rail" : ""}`}>
        <header className="rail-head">
          <div>
            <h2>{title}</h2>
            {kicker ? <p>{kicker}</p> : null}
          </div>
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
          <h2>{title}</h2>
          {kicker ? <p>{kicker}</p> : null}
        </div>
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
