/** Household indexer call budget captions for Maintain. Never per-reader. */

export function indexerBudgetHosts(body) {
  const hosts = body?.indexer_budget?.hosts;
  if (!Array.isArray(hosts)) return [];
  return hosts.filter((host) => host && typeof host.id === "string");
}

export function indexerBudgetCaption(host) {
  const name = String(host?.name || host?.id || "Indexer");
  const calls = Number(host?.calls) || 0;
  const budget = Number(host?.budget) || 0;
  const wanted = Number(host?.wanted_calls) || 0;
  const wantedBudget = Number(host?.wanted_budget) || 0;
  return `${name} · ${calls} / ${budget} (Wanted ${wanted} / ${wantedBudget})`;
}

export function pollerStepCaption(step) {
  const label = String(step?.label || step?.id || "Check");
  if (step?.state === "off") {
    const reason = String(step?.off_reason || "").trim() || "Off: not configured";
    return `${label} · ${reason}`;
  }
  return "";
}
