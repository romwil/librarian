import { useEffect, useState } from "react";

/** In-place wait. The status line starts as Thinking… and becomes Still thinking… if the request lingers. */
export const THINKING_LONG_AFTER_MS = 3500;

export function Thinking({
  message = "Thinking…",
  longMessage = "Still thinking…",
  longAfterMs = THINKING_LONG_AFTER_MS,
  inline = false,
  className = "",
  testId,
}) {
  const [longWait, setLongWait] = useState(false);

  useEffect(() => {
    if (longAfterMs == null || longAfterMs < 0) return undefined;
    const timer = window.setTimeout(() => setLongWait(true), longAfterMs);
    return () => window.clearTimeout(timer);
  }, [longAfterMs, message]);

  const Tag = inline ? "span" : "p";
  const words = longWait ? longMessage : message;

  return (
    <Tag
      className={["thinking", inline ? "is-inline" : "", className].filter(Boolean).join(" ")}
      role="status"
      data-testid={testId}
    >
      <span className="thinking-lamp" aria-hidden="true" />
      {words}
    </Tag>
  );
}

export function ThinkingButton({ busy = false, children, className = "", type = "button", disabled = false, ...rest }) {
  return (
    <button
      {...rest}
      type={type}
      className={className}
      disabled={Boolean(disabled) || Boolean(busy)}
      aria-busy={busy ? "true" : undefined}
    >
      {busy ? <Thinking inline /> : children}
    </button>
  );
}
