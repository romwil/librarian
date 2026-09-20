/**
 * Settings page section map — jump nav + deep-link hashes.
 * Setup steps match SetupWizard; Ingest / About are sibling panels.
 */
export const SETTINGS_NAV = [
  { id: "downloader", label: "Downloader", kind: "setup", step: 0 },
  { id: "indexer", label: "Indexer", kind: "setup", step: 1 },
  { id: "shelves", label: "Shelves", kind: "setup", step: 2 },
  { id: "bagging", label: "Bagging", kind: "setup", step: 3 },
  { id: "ingest", label: "Ingest", kind: "panel" },
  { id: "about", label: "About", kind: "panel" },
];

/** Resolve hash → nav item (supports #release-notes → About). */
export function settingsNavFromHash(hash) {
  const raw = String(hash || "")
    .replace(/^#/, "")
    .trim()
    .toLowerCase();
  if (!raw) return null;
  if (raw === "release-notes" || raw === "whats-new") {
    return SETTINGS_NAV.find((item) => item.id === "about") || null;
  }
  return SETTINGS_NAV.find((item) => item.id === raw) || null;
}

export function settingsNavHref(item) {
  return `#${item.id}`;
}
