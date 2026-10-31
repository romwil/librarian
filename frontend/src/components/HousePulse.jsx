import { HOUSE_PULSE_HEADING, HOUSE_PULSE_LEDE } from "../copy.js";
import { pulseNorthStarLine, pulseRows, pulseWeatherWord } from "../lib/housePulse.js";

export default function HousePulse({ pulse, loading = false }) {
  if (loading && !pulse) {
    return (
      <section className="house-pulse" data-testid="house-pulse" aria-label="House pulse" aria-busy="true">
        <p className="kicker">{HOUSE_PULSE_HEADING}</p>
        <h2>How the house is reading</h2>
        <p className="lede">Gathering household totals…</p>
      </section>
    );
  }
  if (!pulse) return null;
  const rows = pulseRows(pulse);
  const weather = pulseWeatherWord(pulse.weather);
  const star = pulseNorthStarLine(pulse.north_star);

  return (
    <section className="house-pulse" data-testid="house-pulse" aria-label="House pulse">
      <p className="kicker">{HOUSE_PULSE_HEADING}</p>
      <h2>How the house is reading</h2>
      <p className="lede">{HOUSE_PULSE_LEDE}</p>
      <p className="house-pulse-star" data-testid="house-pulse-north-star">
        <span className="kicker">{pulse.north_star?.label || "Volumes read or listened this week"}</span>
        <strong>{star}</strong>
        <span className="muted"> · {weather}</span>
      </p>
      <dl className="house-pulse-rows">
        {rows.map((row) => (
          <div key={row.id} className="house-pulse-row">
            <dt>{row.label}</dt>
            <dd>{row.value}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
