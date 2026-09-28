import { Link } from "react-router-dom";
import { briefIsEmpty, briefPresence } from "../lib/morningBrief.js";

/** Stagger index for settle-in tend cards (CSS --settle-i). */
function settleStyle(index) {
  return { "--settle-i": String(index) };
}

function itemLabel(item) {
  return item.label || item.title || "Tend";
}

function itemPresence(item) {
  return item.presence || item.detail || "";
}

/**
 * Owner Maintain morning desk — tend these three, not a scoreboard.
 * @param {{ brief?: object | null, loading?: boolean }} props
 */
export default function MorningBrief({ brief, loading = false }) {
  if (loading && !brief) {
    return (
      <section
        className="morning-brief morning-brief-alive morning-brief-quiet"
        data-testid="morning-brief"
        aria-label="Morning desk"
        aria-busy="true"
      >
        <span className="morning-brief-glow" aria-hidden="true" />
        <p className="kicker">Morning desk</p>
        <h2 className="morning-brief-title">Tend these three.</h2>
        <p className="morning-brief-presence" data-testid="morning-brief-presence">
          The lamp is still looking…
        </p>
      </section>
    );
  }

  if (!brief) return null;

  if (briefIsEmpty(brief)) {
    return (
      <section
        className="morning-brief morning-brief-alive morning-brief-quiet"
        data-testid="morning-brief"
        aria-label="Morning desk"
      >
        <span className="morning-brief-glow" aria-hidden="true" />
        <p className="kicker">Morning desk</p>
        <h2 className="morning-brief-title">Tend these three.</h2>
        <p className="morning-brief-presence" data-testid="morning-brief-presence">
          <span data-testid="morning-brief-empty">{briefPresence(brief)}</span>
        </p>
      </section>
    );
  }

  const items = Array.isArray(brief.items) ? brief.items : [];

  return (
    <section
      className="morning-brief morning-brief-alive"
      data-testid="morning-brief"
      aria-label="Morning desk"
    >
      <span className="morning-brief-glow" aria-hidden="true" />
      <p className="kicker">Morning desk</p>
      <h2 className="morning-brief-title">Tend these three.</h2>
      <p className="morning-brief-presence" data-testid="morning-brief-presence">
        {briefPresence(brief)}
      </p>
      <ul className="morning-brief-list">
        {items.map((item, index) => {
          const breathing = Boolean(item.breathing);
          return (
            <li
              key={item.id || item.kind || index}
              className={
                breathing
                  ? "morning-brief-slot morning-brief-row cover-settle is-breathing"
                  : "morning-brief-slot morning-brief-row cover-settle"
              }
              style={settleStyle(index)}
              data-testid="morning-brief-item"
              data-kind={item.kind || ""}
            >
              <p className="morning-brief-label">{itemLabel(item)}</p>
              <p className="morning-brief-item-presence">{itemPresence(item)}</p>
              {item.href ? (
                <Link className="cta outline compact" to={item.href}>
                  {item.cta || "Tend"}
                </Link>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
