import assert from "node:assert/strict";
import { test } from "node:test";
import { SETTINGS_NAV, settingsNavFromHash, settingsNavHref } from "./settingsNav.js";

test("SETTINGS_NAV lists setup steps then Ingest and About", () => {
  const labels = SETTINGS_NAV.map((item) => item.label);
  assert.deepEqual(labels, ["Downloader", "Indexer", "Shelves", "Bagging", "Ingest", "About"]);
  assert.equal(SETTINGS_NAV.filter((item) => item.kind === "setup").length, 4);
  assert.ok(SETTINGS_NAV.find((item) => item.id === "ingest"));
  assert.ok(SETTINGS_NAV.find((item) => item.id === "about"));
});

test("settingsNavFromHash maps release-notes to About", () => {
  assert.equal(settingsNavFromHash("#about")?.id, "about");
  assert.equal(settingsNavFromHash("#release-notes")?.id, "about");
  assert.equal(settingsNavFromHash("#whats-new")?.id, "about");
  assert.equal(settingsNavFromHash("#ingest")?.id, "ingest");
  assert.equal(settingsNavFromHash("#downloader")?.step, 0);
  assert.equal(settingsNavFromHash("#missing"), null);
});

test("settingsNavHref builds section hashes", () => {
  assert.equal(settingsNavHref({ id: "ingest" }), "#ingest");
});
