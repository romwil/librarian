import { Link } from "react-router-dom";
import { findHref, gapFindFields } from "../find.js";
import { catchUpCtaLabel } from "../lib/seriesCatchUp.js";

/** Stagger index for settle-in rows (CSS --settle-i). */
function settleStyle(index) {
  return { "--settle-i": String(index) };
}

export default function SeriesCatchUp({ catchUp, role = "reader" }) {
  const series = catchUp?.series || [];
  if (!catchUp || catchUp.empty || !series.length) return null;
  const cta = catchUpCtaLabel(role);

  return (
    <section
      className="series-catch-up series-catch-up-alive"
      data-testid="series-catch-up"
      aria-label="Series catch-up"
    >
      <span className="series-catch-up-glow" aria-hidden="true" />
      <p className="kicker">Series catch-up</p>
      <h2 className="series-catch-up-title">A hole or two from whole</h2>
      <p className="series-catch-up-presence">
        No hurry — these runs are nearly complete on your shelves.
      </p>
      <ul className="series-catch-up-list">
        {series.map((row, index) => {
          const href = row.next_gap
            ? findHref(gapFindFields({ ...row.next_gap, gap: true }))
            : "";
          const beads = row.ribbon || [];
          return (
            <li
              className="series-catch-up-row cover-settle"
              key={row.id}
              style={settleStyle(index)}
              data-testid="series-catch-up-row"
            >
              <p className="series-catch-up-series">{row.series_name}</p>
              <p className="series-catch-up-invitation">{row.invitation}</p>
              {row.author ? <p className="muted">{row.author}</p> : null}
              {beads.length ? (
                <div
                  className="series-catch-up-track"
                  role="img"
                  aria-label={`On the shelf, missing ${row.missing.join(", ")}`}
                >
                  {beads.map((bead) => (
                    <span key={bead.value} className={`series-bead is-${bead.state}`} />
                  ))}
                </div>
              ) : null}
              {href ? (
                <Link className="cta outline compact" to={href}>
                  {cta}
                </Link>
              ) : null}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
