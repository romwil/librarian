import { Link } from "react-router-dom";
import { pulseClass, scoreIsCalm, scorePresence, scoreTend } from "../lib/shelfHealthScore.js";

/**
 * Living shelf pulse — weather + one tend action.
 * @param {{ score?: object | null }} props
 */
export default function ShelfHealthPulse({ score = null }) {
  if (!score) return null;

  const calm = scoreIsCalm(score);
  const tend = scoreTend(score);
  const weather = pulseClass(score);

  return (
    <div
      className={`shelf-health-pulse shelf-health-pulse-${weather}${calm ? " is-calm" : " is-alive"}`}
      data-testid="shelf-health-pulse"
      data-pulse={weather}
      aria-label="Shelf pulse"
    >
      <span className="shelf-health-pulse-glow" aria-hidden="true" />
      <p className="kicker">Shelf pulse</p>
      <p className="shelf-health-pulse-presence" data-testid="shelf-health-pulse-presence">
        {scorePresence(score)}
      </p>
      {tend ? (
        <p className="shelf-health-pulse-tend" data-testid="shelf-health-pulse-tend">
          <Link className="cta outline compact" to={tend.href}>
            {tend.cta}
          </Link>
        </p>
      ) : null}
    </div>
  );
}
