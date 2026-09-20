import assert from "node:assert/strict";
import test from "node:test";
import {
  FONT_STEP_MAX,
  applyUiTheme,
  cycleUiTheme,
  loadStoredUiFontStep,
  loadStoredUiTheme,
  normalizeUiFontStep,
  normalizeUiTheme,
  persistUiFontStep,
  resolveEffectiveTheme,
  themeControlGlyph,
  themePreferenceLabel,
  themeToDataAttr,
} from "./uiPrefs.js";

test("normalizeUiFontStep clamps to 0..5", () => {
  assert.equal(normalizeUiFontStep(0), 0);
  assert.equal(normalizeUiFontStep(5), 5);
  assert.equal(normalizeUiFontStep(FONT_STEP_MAX), 5);
  assert.equal(normalizeUiFontStep(99), 5);
  assert.equal(normalizeUiFontStep(-3), 0);
  assert.equal(normalizeUiFontStep("3"), 3);
  assert.equal(normalizeUiFontStep(null), 0);
  assert.equal(normalizeUiFontStep("huge"), 0);
});

test("normalizeUiTheme accepts lights_up lights_down system", () => {
  assert.equal(normalizeUiTheme("lights_up"), "lights_up");
  assert.equal(normalizeUiTheme("lights_down"), "lights_down");
  assert.equal(normalizeUiTheme("system"), "system");
});

test("normalizeUiTheme defaults invalid values to system", () => {
  assert.equal(normalizeUiTheme("dark"), "system");
  assert.equal(normalizeUiTheme(null), "system");
  assert.equal(normalizeUiTheme(""), "system");
});

test("resolveEffectiveTheme passes through explicit prefs", () => {
  assert.equal(resolveEffectiveTheme("lights_up"), "lights_up");
  assert.equal(resolveEffectiveTheme("lights_down"), "lights_down");
});

test("resolveEffectiveTheme uses matchMedia for system", () => {
  assert.equal(resolveEffectiveTheme("system", { matches: true }), "lights_up");
  assert.equal(resolveEffectiveTheme("system", { matches: false }), "lights_down");
  assert.equal(
    resolveEffectiveTheme("system", (q) => ({ matches: q.includes("light") })),
    "lights_up",
  );
});

test("themeToDataAttr maps underscores to hyphenated data-theme", () => {
  assert.equal(themeToDataAttr("lights_up"), "lights-up");
  assert.equal(themeToDataAttr("lights_down"), "lights-down");
});

test("cycleUiTheme rotates preference order", () => {
  assert.equal(cycleUiTheme("lights_up"), "lights_down");
  assert.equal(cycleUiTheme("lights_down"), "system");
  assert.equal(cycleUiTheme("system"), "lights_up");
});

test("themePreferenceLabel and themeControlGlyph", () => {
  assert.equal(themePreferenceLabel("lights_up"), "Lights Up");
  assert.equal(themePreferenceLabel("lights_down"), "Lights Down");
  assert.equal(themePreferenceLabel("system"), "Match system");
  assert.equal(themeControlGlyph("system"), "◐");
  assert.equal(themeControlGlyph("lights_up"), "☀");
  assert.equal(themeControlGlyph("lights_down"), "☾");
});

test("applyUiTheme persists preference without document", () => {
  const store = new Map();
  const storage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, v),
  };
  const result = applyUiTheme("lights_up", { storage, media: { matches: false } });
  assert.equal(result.preference, "lights_up");
  assert.equal(result.effective, "lights_up");
  assert.equal(store.get("librarian.ui_theme"), "lights_up");
});

test("loadStoredUiTheme defaults to system when unset", () => {
  const store = new Map();
  const storage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, v),
  };
  assert.equal(loadStoredUiTheme(storage), "system");
});

test("font step persist and load round-trip", () => {
  const store = new Map();
  const storage = {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => store.set(k, v),
  };
  assert.equal(loadStoredUiFontStep(storage), 0);
  assert.equal(persistUiFontStep(4, storage), 4);
  assert.equal(loadStoredUiFontStep(storage), 4);
  assert.equal(persistUiFontStep(99, storage), 5);
  assert.equal(loadStoredUiFontStep(storage), 5);
});
