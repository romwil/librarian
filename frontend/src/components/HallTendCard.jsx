import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import MorningBrief from "./MorningBrief.jsx";

/**
 * Owner Hall tend card — deep-links the same Maintain "Tend these…" brief.
 * Does not invent a third morning narrative (PRD-009).
 */
export default function HallTendCard() {
  const [brief, setBrief] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api
      .maintainMorningBrief()
      .then((data) => {
        if (!cancelled) {
          setBrief(data);
          setLoading(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setBrief(null);
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!loading && !brief) return null;
  if (!loading && brief?.empty) return null;

  return (
    <section className="hall-tend" data-testid="hall-tend" aria-label="Tend these">
      <MorningBrief brief={brief} loading={loading} />
      <p className="hall-tend-maintain muted">
        <Link to="/maintain" data-testid="hall-tend-maintain">
          Open Maintain morning desk
        </Link>
      </p>
    </section>
  );
}
