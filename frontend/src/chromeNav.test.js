import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const root = dirname(fileURLToPath(import.meta.url));
const chromeSrc = readFileSync(join(root, "components/AppChrome.jsx"), "utf8");
const menuSrc = readFileSync(join(root, "components/ProfileMenu.jsx"), "utf8");
const mainSrc = readFileSync(join(root, "main.jsx"), "utf8");

test("top nav is Hall, Search, Wanted, with Downloads and Holds for owner and op", () => {
  assert.match(chromeSrc, />\s*Hall\s*</);
  assert.match(chromeSrc, />\s*Search\s*</);
  assert.match(chromeSrc, />\s*Wanted\s*</);
  assert.match(chromeSrc, />\s*Downloads\s*</);
  assert.match(chromeSrc, /holdsLabel/);
  assert.match(chromeSrc, /Holds \$\{reviewCount\}/);
  assert.equal(chromeSrc.includes("Stacks"), false);
  assert.equal(chromeSrc.includes(">Noted<"), false);
  assert.equal(chromeSrc.includes("Favorites"), false);
  assert.equal(chromeSrc.includes("Review bag"), false);
  assert.equal(chromeSrc.includes("bag-glyph"), false);
  assert.equal(chromeSrc.includes("review-bag"), false);
  assert.equal(chromeSrc.includes("LampMark"), false);
  assert.match(chromeSrc, /user\.role === "owner" \|\| user\.role === "op"/);
});

test("account menu holds theme, lamp, People, Maintain, and Settings", () => {
  assert.match(menuSrc, /profile-theme-section/);
  assert.match(menuSrc, /profile-ambient-section/);
  assert.match(menuSrc, />\s*People\s*</);
  assert.match(menuSrc, />\s*Maintain\s*</);
  assert.match(menuSrc, />\s*Settings\s*</);
  assert.match(menuSrc, />\s*Downloads\s*</);
  assert.match(menuSrc, />\s*Holds\s*</);
  assert.equal(chromeSrc.includes("theme-toggle"), false);
  assert.equal(chromeSrc.includes("ambient-toggle"), false);
});

test("/browse redirects to Hall", () => {
  assert.match(mainSrc, /function BrowseToHall/);
  assert.match(mainSrc, /path="browse" element=\{<BrowseToHall/);
  assert.match(mainSrc, /pathname: "\/"/);
});
