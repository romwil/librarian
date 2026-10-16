import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const root = dirname(fileURLToPath(import.meta.url));
const hallSrc = readFileSync(join(root, "pages/HallPage.jsx"), "utf8");
const maintainSrc = readFileSync(join(root, "pages/MaintainPage.jsx"), "utf8");
const mainSrc = readFileSync(join(root, "main.jsx"), "utf8");

test("Hall is the collection — kind, shelf, and sort, then covers", () => {
  assert.equal(hallSrc.includes("bestsellersHref"), false);
  assert.equal(hallSrc.includes("bestsellers-door"), false);
  assert.equal(hallSrc.includes("AddToLibrary"), false);
  assert.equal(hallSrc.includes("hall-ingest"), false);
  assert.equal(hallSrc.includes("CelebrationBanner"), false);
  assert.equal(hallSrc.includes("celebration-banner"), false);
  assert.equal(hallSrc.includes("ShelfMore"), false);
  assert.equal(hallSrc.includes("What are you looking for?"), false);
  assert.match(hallSrc, /HallCollection/);
  assert.match(hallSrc, /title="Continue reading"/);
  assert.match(hallSrc, /title="Continue listening"/);
  assert.match(hallSrc, /title="Recently added"/);
  assert.match(hallSrc, /continueRailItems/);
  assert.match(hallSrc, /New & noted/);
});

test("Maintain is owner-only and houses grooming entry points", () => {
  assert.match(maintainSrc, /role !== "owner"/);
  assert.match(maintainSrc, /Navigate to="\/"/);
  assert.match(maintainSrc, /bestsellersHref/);
  assert.match(maintainSrc, /AddToLibrary/);
  assert.match(maintainSrc, /MorningBrief/);
  assert.match(maintainSrc, /maintain-scan/);
  assert.match(maintainSrc, /maintain-clear-extra-files/);
  assert.match(maintainSrc, /MaintainStatusDock/);
  assert.match(maintainSrc, /maintain-shelf-health/);
  assert.match(maintainSrc, /Shelf health/);
});

test("main routes include /maintain", () => {
  assert.match(mainSrc, /path="maintain"/);
  assert.match(mainSrc, /MaintainPage/);
});
