/**
 * Warm lamp loading — shared skeleton so pages never flash empty.
 * Copy stays lexicon-friendly ("Warming the lamp…").
 */
export default function WarmLoad({
  message = "Warming the lamp…",
  testId = "warm-load",
  className = "",
}) {
  return (
    <section
      className={["warm-load", className].filter(Boolean).join(" ")}
      data-testid={testId}
      aria-busy="true"
    >
      <p className="muted">{message}</p>
      <div className="warm-load-skeleton" aria-hidden="true" />
    </section>
  );
}
