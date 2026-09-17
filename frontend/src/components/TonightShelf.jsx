import { Link } from "react-router-dom";
import { discoverHref, findHref, gapFindFields } from "../find.js";
import CoverCard from "./CoverCard.jsx";

export default function TonightShelf({ tonight, role = "reader" }) {
  if (!tonight || tonight.empty) return null;
  const cont = tonight.continue;
  const gap = tonight.gap;
  const surprise = tonight.surprise;
  const gapHref = gap ? findHref(gapFindFields({ ...gap, gap: true })) : "";

  return (
    <section className="tonight-shelf" data-testid="tonight-shelf">
      <p className="kicker">Tonight’s shelf</p>
      <h2 className="tonight-title">Pick up where you left the lamp</h2>
      <div className="tonight-grid">
        {cont ? (
          <div className="tonight-slot" data-testid="tonight-continue">
            <p className="tonight-label">Continue</p>
            <CoverCard work={cont} role={role} />
          </div>
        ) : null}
        {gap ? (
          <div className="tonight-slot" data-testid="tonight-gap">
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
          <div className="tonight-slot" data-testid="tonight-surprise">
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
