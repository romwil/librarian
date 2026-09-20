/** Theme + text-size prefs — Projectionist-shaped, Librarian keys. */

/** Six steps: 0 = current default, 1–5 = larger. Far left of the slider is 0. */
export const FONT_STEPS = ["15px", "16px", "17px", "18.5px", "20px", "22px"];
export const FONT_STEP_MAX = FONT_STEPS.length - 1;
export const FONT_STEP_DEFAULT = 0;

export const UI_THEME_STORAGE_KEY = "librarian.ui_theme";
export const UI_FONT_STEP_STORAGE_KEY = "librarian.ui_font_step";

const THEME_PREFS = new Set(["lights_up", "lights_down", "system"]);

export function normalizeUiFontStep(step) {
  const n = Number.parseInt(step, 10);
  if (!Number.isFinite(n)) return FONT_STEP_DEFAULT;
  if (n < 0) return 0;
  if (n > FONT_STEP_MAX) return FONT_STEP_MAX;
  return n;
}

/** Apply preferred base font size via CSS variable on :root. */
export function applyUiFontStep(step) {
  const key = normalizeUiFontStep(step);
  const px = FONT_STEPS[key];
  if (typeof document !== "undefined") {
    document.documentElement.style.setProperty("--base-font-size", px);
    document.documentElement.dataset.fontStep = String(key);
  }
  return key;
}

export function loadStoredUiFontStep(storage = globalThis.localStorage) {
  try {
    const current = storage?.getItem?.(UI_FONT_STEP_STORAGE_KEY);
    if (current != null && String(current).trim() !== "") {
      return normalizeUiFontStep(current);
    }
    return FONT_STEP_DEFAULT;
  } catch {
    return FONT_STEP_DEFAULT;
  }
}

export function persistUiFontStep(step, storage = globalThis.localStorage) {
  const normalized = normalizeUiFontStep(step);
  try {
    storage?.setItem?.(UI_FONT_STEP_STORAGE_KEY, String(normalized));
  } catch {
    // localStorage unavailable
  }
  return normalized;
}

export function normalizeUiTheme(theme) {
  const cleaned = String(theme ?? "system")
    .trim()
    .toLowerCase();
  return THEME_PREFS.has(cleaned) ? cleaned : "system";
}

/**
 * Resolve preference → effective theme (`lights_up` | `lights_down`).
 * @param {string} pref
 * @param {{ matches?: boolean } | ((query: string) => { matches: boolean }) | null} [media]
 */
export function resolveEffectiveTheme(pref, media) {
  const normalized = normalizeUiTheme(pref);
  if (normalized !== "system") return normalized;

  let prefersLight = false;
  try {
    if (media && typeof media === "object" && "matches" in media) {
      prefersLight = Boolean(media.matches);
    } else if (typeof media === "function") {
      prefersLight = Boolean(media("(prefers-color-scheme: light)")?.matches);
    } else if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
      prefersLight = Boolean(window.matchMedia("(prefers-color-scheme: light)").matches);
    }
  } catch {
    prefersLight = false;
  }
  return prefersLight ? "lights_up" : "lights_down";
}

/** Map effective theme to `html[data-theme]`. */
export function themeToDataAttr(effective) {
  return effective === "lights_up" ? "lights-up" : "lights-down";
}

export function loadStoredUiTheme(storage = globalThis.localStorage) {
  try {
    const current = storage?.getItem?.(UI_THEME_STORAGE_KEY);
    if (current != null && String(current).trim() !== "") {
      return normalizeUiTheme(current);
    }
    return "system";
  } catch {
    return "system";
  }
}

export function persistUiTheme(theme, storage = globalThis.localStorage) {
  const normalized = normalizeUiTheme(theme);
  try {
    storage?.setItem?.(UI_THEME_STORAGE_KEY, normalized);
  } catch {
    // localStorage unavailable
  }
  return normalized;
}

/**
 * Apply theme preference to the document and optionally persist to localStorage.
 * @returns {{ preference: string, effective: string }}
 */
export function applyUiTheme(theme, { persist = true, media, storage } = {}) {
  const preference = normalizeUiTheme(theme);
  const effective = resolveEffectiveTheme(preference, media);
  if (typeof document !== "undefined") {
    document.documentElement.dataset.theme = themeToDataAttr(effective);
    document.documentElement.style.colorScheme = effective === "lights_up" ? "light" : "dark";
  }
  if (persist) {
    persistUiTheme(preference, storage);
  }
  return { preference, effective };
}

/** Cycle Lights Up → Lights Down → Match system. */
export function cycleUiTheme(current) {
  const order = ["lights_up", "lights_down", "system"];
  const idx = order.indexOf(normalizeUiTheme(current));
  return order[(idx + 1) % order.length];
}

export function themePreferenceLabel(pref) {
  switch (normalizeUiTheme(pref)) {
    case "lights_up":
      return "Lights Up";
    case "lights_down":
      return "Lights Down";
    default:
      return "Match system";
  }
}

/** Short glyph for the topbar toggle (no Material Symbols dependency). */
export function themeControlGlyph(pref, media) {
  const preference = normalizeUiTheme(pref);
  if (preference === "system") return "◐";
  return resolveEffectiveTheme(preference, media) === "lights_up" ? "☀" : "☾";
}
