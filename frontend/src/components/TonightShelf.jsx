import { Link } from "react-router-dom";
import { discoverHref, findHref, gapFindFields } from "../find.js";
import CoverCard from "./CoverCard.jsx";

/** Stagger index for settle-in covers (CSS --settle-i). */
function settleStyle(index) {
  return { "--settle-i": String(index) };
}

export default function TonightShelf({ tonight, role = "reader" }) {
  if (!tonight || tonight.empty) return null;
  const cont = tonight.continue;
  const gap = tonight.gap;
  const surprise = tonight.surprise;
  const gapHref = gap ? findHref(gapFindFields({ ...gap, gap: true })) : "";
  let settle = 0;

  return (
    <section
      className="tonight-shelf tonight-shelf-alive"
      data-testid="tonight-shelf"
      aria-label="Tonight’s shelf"
    >
      <span className="tonight-lamp-glow" aria-hidden="true" />
      <p className="kicker">Tonight’s shelf</p>
      <h2 className="tonight-title">Pick up where you left the lamp</h2>
      <p className="tonight-presence">The room kept your place.</p>
      <div className="tonight-grid">
        {cont ? (
          <div
            className="tonight-slot cover-settle"
            data-testid="tonight-continue"
            style={settleStyle(settle++)}
          >
            <p className="tonight-label">Continue</p>
            <CoverCard work={cont} role={role} />
          </div>
        ) : null}
        {gap ? (
          <div
            className="tonight-slot cover-settle"
            data-testid="tonight-gap"
            style={settleStyle(settle++)}
          >
            <p className="tonight-label">Quick gap</p>
            <CoverCard work={{ ...gap, gap: true }} role={role} />
            {gapHref ? (
              <Link className="cta outline compact" to={gapHref}>
                Fill this hole
              </Link>
            ) : null}
          </div>
        ) : null}
        {surprise ? (
          <div
            className="tonight-slot cover-settle"
            data-testid="tonight-surprise"
            style={settleStyle(settle++)}
          >
            <p className="tonight-label">Surprise</p>
            <CoverCard work={surprise} role={role} />
            <Link className="muted" to={discoverHref()}>
              More from Discover
            </Link>
          </div>
        ) : null}
      </div>
    </section>
  );
}
