/** Continue / noted rails render only when they have titles. */

export function continueRailItems(items) {
  if (!Array.isArray(items) || items.length === 0) return null;
  return items;
}

/** Titles from a New & noted payload. Empty lanes produce no rail. */
export function notedRailItems(payload) {
  const seen = new Set();
  const items = [];
  for (const lane of payload?.lanes || []) {
    for (const card of lane?.items || []) {
      const title = String(card?.title || "").trim();
      if (!title) continue;
      const author = String(card?.author || "").trim();
      const isbn = String(card?.isbn || "").trim();
      const key = `${title.toLowerCase()}|${author.toLowerCase()}|${isbn}`;
      if (seen.has(key)) continue;
      seen.add(key);
      const shelved = card?.shelved?.id
        ? card.shelved
        : card?.shelved_audiobook?.id
          ? card.shelved_audiobook
          : null;
      items.push({
        key,
        title,
        author,
        href: shelved?.id
          ? `/works/${shelved.id}`
          : `/search?q=${encodeURIComponent([author, title].filter(Boolean).join(" "))}`,
      });
      if (items.length >= 12) return items;
    }
  }
  return items.length ? items : null;
}
