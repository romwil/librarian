import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "vitest";
import { pulseNorthStarLine, pulseRows, pulseWeatherWord } from "./housePulse.js";

const root = dirname(fileURLToPath(import.meta.url));
const maintainSrc = readFileSync(join(root, "../pages/MaintainPage.jsx"), "utf8");
const apiSrc = readFileSync(join(root, "../api.js"), "utf8");

test("north star hides member figures under three", () => {
  assert.equal(pulseNorthStarLine({ suppressed: true, value: 12 }), "fewer than 3");
  assert.equal(pulseNorthStarLine({ suppressed: false, value: 4, display: "4" }), "4");
  assert.equal(pulseWeatherWord("act"), "Act");
});

test("operational rows always render", () => {
  const rows = pulseRows({
    asks_filed: { label: "Asks filed this week", value: 2 },
    confirms_waiting: { label: "Confirms waiting", value: 1 },
    arrived: { label: "Arrived this week", value: 3 },
    beyond_error_rate: { label: "Beyond", display: "0 of 10" },
    snapshot_age: { label: "Last backup", display: "No backup yet" },
  });
  assert.equal(rows.length, 5);
  assert.equal(rows[0].value, 2);
  assert.equal(rows[4].value, "No backup yet");
});

test("Maintain loads House pulse from /api/pulse", () => {
  assert.match(maintainSrc, /HousePulse/);
  assert.match(apiSrc, /pulse: \(\) => request\("\/pulse"\)/);
});
