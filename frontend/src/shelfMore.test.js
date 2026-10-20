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

test("Hall shows the catalog on the page and does not hide it behind More shelves", () => {
  assert.equal(hallSrc.includes("ShelfMore"), false);
  assert.match(hallSrc, /HallCollection/);
  assert.match(hallSrc, /TonightShelf/);
  assert.match(hallSrc, /Continue reading/);
  const shelvesAt = hallSrc.indexOf('data-testid="hall-shelves"');
  const collectionAt = hallSrc.indexOf("<HallCollection");
  assert.ok(shelvesAt > 0 && collectionAt > shelvesAt);
});

test("Search shows local hits first, then Beyond, without More shelves", () => {
  const railAt = searchSrc.indexOf('title="On the shelf"');
  const beyondAt = searchSrc.indexOf("search-beyond");
  assert.ok(railAt > 0);
  assert.ok(beyondAt > railAt);
  assert.equal(searchSrc.includes("ShelfMore"), false);
  assert.equal(searchSrc.includes("discover-door"), false);
  assert.equal(searchSrc.includes("find-beyond-cta"), false);
});
