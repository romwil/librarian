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
    confirm_download: { label: "Confirms this week", display: "4 · ~12 ms", value: 4 },
    arrived: { label: "Arrived this week", value: 3 },
    beyond_error_rate: { label: "Beyond", display: "0 of 10" },
    snapshot_age: { label: "Last backup", display: "No backup yet" },
  });
  assert.equal(rows.length, 6);
  assert.equal(rows[0].value, 2);
  assert.equal(rows[2].value, "4 · ~12 ms");
  assert.equal(rows[5].value, "No backup yet");
});

test("ISBN auto-file pulse rows appear only when measured", () => {
  const quiet = pulseRows({
    asks_filed: { value: 0 },
    confirms_waiting: { value: 0 },
    confirm_download: { display: "No confirms this week", value: 0 },
    arrived: { value: 0 },
    beyond_error_rate: { display: "No beyond searches this week" },
    snapshot_age: { display: "No backup yet" },
    isbn_auto_file: { label: "ISBN auto-filed this week", value: 0 },
    isbn_auto_file_undo: { label: "undos", value: 0 },
  });
  assert.equal(quiet.length, 6);
  const live = pulseRows({
    asks_filed: { value: 0 },
    confirms_waiting: { value: 0 },
    confirm_download: { display: "No confirms this week", value: 0 },
    arrived: { value: 0 },
    beyond_error_rate: { display: "No beyond searches this week" },
    snapshot_age: { display: "No backup yet" },
    isbn_auto_file: { label: "ISBN auto-filed this week", value: 2 },
    isbn_auto_file_undo: { label: "ISBN auto-file undos (mis-shelve signal)", value: 1 },
  });
  assert.equal(live.length, 8);
  assert.equal(live[6].value, 2);
  assert.equal(live[7].value, 1);
});

test("Maintain loads House pulse from /api/pulse", () => {
  assert.match(maintainSrc, /HousePulse/);
  assert.match(apiSrc, /pulse: \(\) => request\("\/pulse"\)/);
});
