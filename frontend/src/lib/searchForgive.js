/** Search that forgives — did-you-mean helpers. */

export function didYouMeanList(result) {
  const rows = result?.did_you_mean;
  if (!Array.isArray(rows)) return [];
  return rows.map((item) => String(item || "").trim()).filter(Boolean).slice(0, 3);
}

export function searchForgave(result) {
  return Boolean(result?.forgave);
}

export function didYouMeanPresence(suggestions) {
  const list = Array.isArray(suggestions) ? suggestions : [];
  if (!list.length) return "";
  if (list.length === 1) return `Did you mean “${list[0]}”?`;
  return "Did you mean one of these?";
}
