import { useEffect, useState } from "react";

/**
 * Warm lamp loading — shared skeleton so pages never flash empty.
 * Copy stays lexicon-friendly ("Warming the lamp…").
 * After a short wait the message acknowledges a long throb without lying forever.
 */
export default function WarmLoad({
  message = "Warming the lamp…",
  longMessage = "Still warming the lamp…",
  longAfterMs = 3500,
  testId = "warm-load",
  className = "",
}) {
  const [longWait, setLongWait] = useState(false);

  useEffect(() => {
    if (!longAfterMs || longAfterMs < 0) return undefined;
    const timer = window.setTimeout(() => setLongWait(true), longAfterMs);
    return () => window.clearTimeout(timer);
  }, [longAfterMs, message]);

  return (
    <section
      className={["warm-load", className].filter(Boolean).join(" ")}
      data-testid={testId}
      aria-busy="true"
    >
      <p className="muted">{longWait ? longMessage : message}</p>
      <div className="warm-load-skeleton" aria-hidden="true" />
    </section>
  );
}
