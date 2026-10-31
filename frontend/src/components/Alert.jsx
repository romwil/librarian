/** Shared live region. `assertive` for errors; `status` for quiet confirmations. */
export default function Alert({ children, tone = "assertive", className = "" }) {
  const status = tone === "status" || tone === "polite";
  return (
    <p
      className={["alert", className].filter(Boolean).join(" ")}
      role={status ? "status" : "alert"}
      aria-live={status ? "polite" : "assertive"}
    >
      {children}
    </p>
  );
}
