/** Named extra-indexer presets. NZBFinder stays first and is not a preset. */

export const DIALECT_NEWZNAB = "newznab";
export const DIALECT_V2 = "v2";

export const DRUNKENSLUG_PRESET = {
  id: "drunkenslug",
  name: "DrunkenSlug",
  url: "https://drunkenslug.com",
  dialect: DIALECT_NEWZNAB,
};

export const INDEXER_PRESETS = [DRUNKENSLUG_PRESET];

function normalizeUrl(url) {
  return String(url || "")
    .trim()
    .replace(/\/+$/, "")
    .toLowerCase();
}

export function extraIndexerRowFromPreset(preset) {
  return {
    id: preset.id,
    name: preset.name,
    url: preset.url,
    api_token: "",
    enabled: true,
    dialect: preset.dialect || "",
  };
}

export function extraIndexersHavePreset(rows, preset) {
  const id = String(preset?.id || "");
  const wantUrl = normalizeUrl(preset?.url);
  const wantName = String(preset?.name || "").toLowerCase();
  return (rows || []).some((row) => {
    const rowId = String(row?.id || "");
    const rowUrl = normalizeUrl(row?.url);
    const rowName = String(row?.name || "").toLowerCase();
    if (id && rowId === id) return true;
    if (wantUrl && rowUrl === wantUrl) return true;
    if (wantName && rowName === wantName) return true;
    return false;
  });
}

export function addIndexerPreset(rows, preset) {
  const current = Array.isArray(rows) ? [...rows] : [];
  if (extraIndexersHavePreset(current, preset)) return current;
  return [...current, extraIndexerRowFromPreset(preset)];
}
