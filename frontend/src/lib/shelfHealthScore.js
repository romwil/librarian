/** Shelf health pulse — weather voice, never a KPI strip. */

export const PULSE_ORDER = ["calm", "stirring", "needs_you"];

/** Prefer server presence; fall back so hostile payloads stay warm. */
export function scorePresence(score) {
  const fromServer = String(score?.presence || "").trim();
  if (fromServer) return fromServer;
  const pulse = String(score?.pulse || "").trim();
  if (pulse === "needs_you") return "A root feels locked for the lamp.";
  if (pulse === "stirring") return "A soft breeze through the stacks.";
  return "The shelves feel settled.";
}

export function scoreIsCalm(score) {
  if (!score) return true;
  if (score.ok === true) return true;
  return String(score.pulse || "") === "calm" || !score.tend;
}

export function scoreTend(score) {
  const tend = score?.tend;
  if (!tend || typeof tend !== "object") return null;
  const cta = String(tend.cta || "").trim();
  const href = String(tend.href || "").trim();
  if (!cta || !href) return null;
  return tend;
}

/** Pulse class token for chrome — never a numeric grade. */
export function pulseClass(score) {
  const pulse = String(score?.pulse || "calm").trim() || "calm";
  if (pulse === "needs_you" || pulse === "stirring") return pulse;
  return "calm";
}
