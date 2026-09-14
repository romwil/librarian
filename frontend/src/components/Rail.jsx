import CoverCard from "./CoverCard.jsx";

export default function Rail({ title, items, empty, onRequest }) {
  if (!items?.length) {
    return empty ? (
      <section className="rail">
        <header className="rail-head">
          <h2>{title}</h2>
        </header>
        <p className="muted">{empty}</p>
      </section>
    ) : null;
  }
  return (
    <section className="rail">
      <header className="rail-head">
        <h2>{title}</h2>
      </header>
      <div className="rail-track">
        {items.map((item) => (
          <CoverCard key={item.id || item.guid || item.title} work={item} onRequest={onRequest} />
        ))}
      </div>
    </section>
  );
}
