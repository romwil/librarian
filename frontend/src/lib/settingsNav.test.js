import assert from "node:assert/strict";
import { test } from "node:test";
import { SETTINGS_NAV, settingsNavFromHash, settingsNavHref } from "./settingsNav.js";

test("SETTINGS_NAV lists flat sections without wizard Prev/Next", () => {
  const labels = SETTINGS_NAV.map((item) => item.label);
  assert.deepEqual(labels, [
    "Appearance",
    "Downloader",
    "Indexers",
    "Shelves",
    "Bagging",
    "Language model",
    "Mail",
    "Integrations",
    "Household",
    "Watch folder",
    "About",
  ]);
  assert.equal(SETTINGS_NAV.filter((item) => item.kind === "setup").length, 4);
  assert.ok(SETTINGS_NAV.find((item) => item.id === "indexers"));
  assert.ok(SETTINGS_NAV.find((item) => item.id === "mail"));
  assert.ok(SETTINGS_NAV.find((item) => item.id === "ingest"));
  assert.ok(SETTINGS_NAV.find((item) => item.id === "about"));
  assert.equal(
    SETTINGS_NAV.some((item) => /next|previous|wizard/i.test(item.label)),
    false,
  );
});

test("settingsNavFromHash maps legacy indexer and release-notes", () => {
  assert.equal(settingsNavFromHash("#about")?.id, "about");
  assert.equal(settingsNavFromHash("#release-notes")?.id, "about");
  assert.equal(settingsNavFromHash("#whats-new")?.id, "about");
  assert.equal(settingsNavFromHash("#ingest")?.id, "ingest");
  assert.equal(settingsNavFromHash("#indexers")?.id, "indexers");
  assert.equal(settingsNavFromHash("#indexer")?.id, "indexers");
  assert.equal(settingsNavFromHash("#rss")?.id, "indexers");
  assert.equal(settingsNavFromHash("#downloader")?.step, 0);
  assert.equal(settingsNavFromHash("#missing"), null);
});

test("settingsNavHref builds section hashes", () => {
  assert.equal(settingsNavHref({ id: "ingest" }), "#ingest");
  assert.equal(settingsNavHref({ id: "indexers" }), "#indexers");
});
