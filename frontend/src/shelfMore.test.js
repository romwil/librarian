import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "vitest";

const root = dirname(fileURLToPath(import.meta.url));
const hallSrc = readFileSync(join(root, "pages/HallPage.jsx"), "utf8");
const searchSrc = readFileSync(join(root, "pages/SearchPage.jsx"), "utf8");
const browseSrc = readFileSync(join(root, "pages/BrowsePage.jsx"), "utf8");
const barSrc = readFileSync(join(root, "components/StacksCommandBar.jsx"), "utf8");

test("Hall keeps personalized rails and leaves the catalog grid off the page", () => {
  assert.equal(hallSrc.includes("<NamedShelves"), false);
  assert.match(hallSrc, /Continue reading/);
  assert.match(hallSrc, /Continue listening/);
  assert.match(hallSrc, /New & noted/);
  assert.ok(hallSrc.includes('data-testid="hall-shelves"'));
});

test("Stacks shelf control opens household shelves", () => {
  assert.match(browseSrc, /shelves=\{namedShelves\}/);
  assert.match(browseSrc, /shelfPresence=\{shelfPresence\}/);
  assert.match(browseSrc, /onShelfNamed=\{onShelfNamed\}/);
  assert.equal(browseSrc.includes("<NamedShelves"), false);
  assert.match(barSrc, /<NamedShelves/);
  assert.match(barSrc, /Name a shelf/);
  assert.match(barSrc, /stacks-name-shelf/);
  assert.match(barSrc, /\.map\(\(shelf\)/);
  assert.match(barSrc, />Favorites</);
  assert.equal(hallSrc.includes("<NamedShelves"), false);
});

test("Search shows local hits first, then Beyond, without More shelves", () => {
  const railAt = searchSrc.indexOf('title="On the shelf"');
  const beyondAt = searchSrc.indexOf("search-beyond");
  assert.ok(railAt > 0);
  assert.ok(beyondAt > railAt);
  assert.equal(searchSrc.includes("discover-door"), false);
  assert.equal(searchSrc.includes("find-beyond-cta"), false);
});
