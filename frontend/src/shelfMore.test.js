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
const browseSrc = readFileSync(join(root, "pages/BrowsePage.jsx"), "utf8");
const barSrc = readFileSync(join(root, "components/StacksCommandBar.jsx"), "utf8");

test("More shelves is a closed disclosure, not a second visual system", () => {
  assert.equal(MORE_SHELVES_LABEL, "More shelves");
  assert.match(moreSrc, /className="shelf-more"/);
  assert.match(moreSrc, /aria-expanded=\{open\}/);
  assert.match(moreSrc, /useState\(false\)/);
  assert.match(moreSrc, /hidden=\{!open\}/);
  assert.match(moreSrc, /\{MORE_SHELVES_LABEL\}/);
});

test("Hall keeps personalized rails and leaves the catalog grid off the page", () => {
  assert.equal(hallSrc.includes("ShelfMore"), false);
  assert.equal(hallSrc.includes("HallCollection"), false);
  assert.equal(hallSrc.includes("<NamedShelves"), false);
  assert.match(hallSrc, /TonightShelf/);
  assert.match(hallSrc, /Continue reading/);
  assert.match(hallSrc, /Continue listening/);
  assert.match(hallSrc, /New & noted/);
  assert.ok(hallSrc.includes('data-testid="hall-shelves"'));
});

test("Stacks shelf control opens household shelves", () => {
  assert.match(browseSrc, /shelves=\{namedShelves\}/);
  assert.match(browseSrc, /<NamedShelves/);
  assert.match(barSrc, /\.map\(\(shelf\)/);
  assert.match(barSrc, />Favorites</);
  assert.equal(hallSrc.includes("<NamedShelves"), false);
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
