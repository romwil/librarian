/**
 * Lamp rituals — thin Hall atmosphere + ceremony helpers.
 * Local-hour only (no server clock); recognition without surveillance.
 */

/** @typedef {"dawn" | "day" | "dusk" | "night"} HallLampPeriod */

/**
 * Map local wall-clock hour to a Hall lamp period.
 * dawn 5–8 · day 8–17 · dusk 17–21 · night otherwise.
 * @param {Date} [date]
 * @returns {HallLampPeriod}
 */
export function hallLampPeriod(date = new Date()) {
  const hour = date instanceof Date && !Number.isNaN(date.getTime()) ? date.getHours() : new Date().getHours();
  if (hour >= 5 && hour < 8) return "dawn";
  if (hour >= 8 && hour < 17) return "day";
  if (hour >= 17 && hour < 21) return "dusk";
  return "night";
}

/** Quiet sr-friendly label for the current period. */
export function hallLampPeriodLabel(period) {
  switch (period) {
    case "dawn":
      return "Dawn in the Hall";
    case "dusk":
      return "Dusk in the Hall";
    case "night":
      return "Night in the Hall";
    default:
      return "Day in the Hall";
  }
}

/**
 * Welcome-back line when Continue (or Continue listening) has volumes waiting.
 * Empty string when nothing waits — no empty ceremony.
 * @param {{ continueCount?: number, listeningCount?: number, period?: HallLampPeriod }} [opts]
 */
export function welcomeBackCopy({ continueCount = 0, listeningCount = 0, period = "day" } = {}) {
  const waiting = Math.max(0, Number(continueCount) || 0) + Math.max(0, Number(listeningCount) || 0);
  if (waiting <= 0) return "";
  if (period === "dawn") return "Welcome back — the lamp kept the early pages.";
  if (period === "dusk") return "Welcome back — volumes wait under the evening lamp.";
  if (period === "night") return "Welcome back — the lamp is still warm.";
  return "Welcome back — something waits under the lamp.";
}

/** Soft finish ceremony line (Work page Finished). */
export function finishRitualCopy() {
  return "The lamp remembers.";
}
