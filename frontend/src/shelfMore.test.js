import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import { MORE_SHELVES_LABEL } from "./copy.js";

const root = dirname(fileURLToPath(import.meta.url));
const hallSrc = readFileSync(join(root, "pages/HallPage.jsx"), "utf8");
const searchSrc = readFileSync(join(root, "pages/SearchPage.jsx"), "utf8");
const moreSrc = readFileSync(join(root, "components/ShelfMore.jsx"), "utf8");

test("More shelves is a closed disclosure, not a second visual system", () => {
  assert.equal(MORE_SHELVES_LABEL, "More shelves");
  assert.match(moreSrc, /className="shelf-more"/);
  assert.match(moreSrc, /aria-expanded=\{open\}/);
  assert.match(moreSrc, /useState\(false\)/);
  assert.match(moreSrc, /hidden=\{!open\}/);
  assert.match(moreSrc, /\{MORE_SHELVES_LABEL\}/);
});

test("Hall keeps living shelves first and folds the catalog behind More shelves", () => {
  const moreAt = hallSrc.indexOf("<ShelfMore>");
  assert.ok(moreAt > 0);
  const before = hallSrc.slice(0, moreAt);
  const after = hallSrc.slice(moreAt);
  for (const mark of [
    "TonightShelf",
    "SeriesCatchUp",
    "Continue listening",
    "Volumes waiting under the lamp",
    "What’s New",
    'title="Favorites"',
  ]) {
    assert.ok(before.includes(mark), mark);
    assert.equal(after.includes(mark), false, mark);
  }
  for (const mark of [
    "<NamedShelves",
    'title="Books"',
    'title="Magazines"',
    'title="Comics"',
    'title="Audiobooks"',
    'title="Incoming Music"',
    "gapsGiftTitle()",
  ]) {
    assert.ok(after.includes(mark), mark);
    assert.equal(before.includes(mark), false, mark);
  }
  assert.match(hallSrc, /<\/ShelfMore>/);
});

test("Search shows local hits first and folds beyond-doors behind More shelves", () => {
  const railAt = searchSrc.indexOf('title="In the stacks"');
  const moreAt = searchSrc.indexOf("<ShelfMore>");
  assert.ok(railAt > 0);
  assert.ok(moreAt > railAt);
  const folded = searchSrc.slice(moreAt);
  assert.match(folded, /discover-door/);
  assert.match(folded, /find-beyond-cta/);
  assert.match(folded, /FIND_BEYOND_CTA/);
  assert.match(folded, /DISCOVER_CTA/);
  assert.equal(searchSrc.slice(0, moreAt).includes("find-beyond-cta"), false);
  assert.equal(searchSrc.slice(0, moreAt).includes("discover-door"), false);
});
