/**
 * Maintain House pulse copy. Household totals only — never a per-member figure.
 */

export function pulseWeatherWord(weather) {
  const key = String(weather || "").trim().toLowerCase();
  if (key === "act") return "Act";
  if (key === "watch") return "Watch";
  return "Steady";
}

export function pulseNorthStarLine(north) {
  if (!north || typeof north !== "object") return "";
  if (north.suppressed) return "fewer than 3";
  if (north.display) return String(north.display);
  if (north.value == null) return "fewer than 3";
  return String(north.value);
}

export function pulseRows(pulse) {
  if (!pulse || typeof pulse !== "object") return [];
  return [
    { id: "asks", label: pulse.asks_filed?.label || "Asks filed this week", value: pulse.asks_filed?.value ?? 0 },
    {
      id: "waiting",
      label: pulse.confirms_waiting?.label || "Confirms waiting",
      value: pulse.confirms_waiting?.value ?? 0,
    },
    { id: "arrived", label: pulse.arrived?.label || "Arrived this week", value: pulse.arrived?.value ?? 0 },
    {
      id: "beyond",
      label: pulse.beyond_error_rate?.label || "Beyond search errors this week",
      value: pulse.beyond_error_rate?.display || "No beyond searches this week",
    },
    {
      id: "backup",
      label: pulse.snapshot_age?.label || "Last backup",
      value: pulse.snapshot_age?.display || "No backup yet",
    },
  ];
}
