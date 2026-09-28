import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const root = dirname(fileURLToPath(import.meta.url));
const appSrc = readFileSync(join(root, "App.jsx"), "utf8");
const hallSrc = readFileSync(join(root, "pages/HallPage.jsx"), "utf8");
const workSrc = readFileSync(join(root, "pages/WorkPage.jsx"), "utf8");
const warmLoadSrc = readFileSync(join(root, "components/WarmLoad.jsx"), "utf8");

test("App boots auth once and soft-refreshes badges without clearing the shell", () => {
  assert.match(appSrc, /}, \[\]\);/);
  assert.match(appSrc, /Soft-refresh bag \+ inbox badges/);
  assert.match(appSrc, /location\.pathname/);
  assert.match(appSrc, /keep last known badges/);
  // Must not reset user to undefined on every route (that re-shows boot-lamp).
  assert.equal(/setUser\(undefined\)/.test(appSrc), false);
});

test("Hall shelves cancel on unmount and acknowledge a long warm", () => {
  assert.match(hallSrc, /cancelled = true/);
  assert.match(hallSrc, /Still warming the shelves/);
  assert.match(hallSrc, /setLongWait\(true\)/);
  assert.match(hallSrc, /3500/);
});

test("WorkPage cancels in-flight detail loads on unmount or id change", () => {
  assert.match(workSrc, /let alive = true/);
  assert.match(workSrc, /alive = false/);
  assert.match(workSrc, /setData\(null\)/);
});

test("WarmLoad acknowledges a long throb without lying forever", () => {
  assert.match(warmLoadSrc, /longMessage/);
  assert.match(warmLoadSrc, /Still warming the lamp/);
  assert.match(warmLoadSrc, /longAfterMs/);
  assert.match(warmLoadSrc, /3500/);
});
