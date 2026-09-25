/**
 * Settings page section map — sticky section list + deep-link hashes.
 * No wizard Prev/Next; each id is a full panel.
 */
export const SETTINGS_NAV = [
  { id: "appearance", label: "Appearance", kind: "panel" },
  { id: "downloader", label: "Downloader", kind: "setup", step: 0 },
  { id: "indexers", label: "Indexers", kind: "setup", step: 1 },
  { id: "shelves", label: "Shelves", kind: "setup", step: 2 },
  { id: "bagging", label: "Bagging", kind: "setup", step: 3 },
  { id: "llm", label: "Language model", kind: "panel" },
  { id: "mail", label: "Mail", kind: "panel" },
  { id: "notifications", label: "Notifications", kind: "panel" },
  { id: "integrations", label: "Integrations", kind: "panel" },
  { id: "household", label: "Household", kind: "panel" },
  { id: "ingest", label: "Watch folder", kind: "panel" },
  { id: "about", label: "About", kind: "panel" },
];

/** Legacy hashes → current section id. */
const HASH_ALIASES = {
  indexer: "indexers",
  "release-notes": "about",
  "whats-new": "about",
  more: "integrations",
  quiet: "household",
  "quiet-hours": "household",
  rss: "indexers",
};

/** Resolve hash → nav item (supports #release-notes → About, #indexer → Indexers). */
export function settingsNavFromHash(hash) {
  const raw = String(hash || "")
    .replace(/^#/, "")
    .trim()
    .toLowerCase();
  if (!raw) return null;
  const id = HASH_ALIASES[raw] || raw;
  return SETTINGS_NAV.find((item) => item.id === id) || null;
}

export function settingsNavHref(item) {
  return `#${item.id}`;
}
