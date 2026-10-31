import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "vitest";
import { readStyles } from "./test/styles.js";

const root = dirname(fileURLToPath(import.meta.url));
const chromeSrc = readFileSync(join(root, "components/AppChrome.jsx"), "utf8");
const menuSrc = readFileSync(join(root, "components/ProfileMenu.jsx"), "utf8");
const mainSrc = readFileSync(join(root, "main.jsx"), "utf8");
const stylesSrc = readStyles();

test("top nav is Hall, Stacks, Search, Favorites, and Wanted, with Downloads and Sorting for owner and op", () => {
  assert.match(chromeSrc, />\s*Hall\s*</);
  assert.match(chromeSrc, />\s*Stacks\s*</);
  assert.match(chromeSrc, />\s*Search\s*</);
  assert.match(chromeSrc, />\s*Favorites\s*</);
  assert.match(chromeSrc, />\s*Wanted\s*</);
  assert.match(chromeSrc, /DOWNLOADS_NAV/);
  assert.match(chromeSrc, /SORTING_NAV/);
  assert.match(chromeSrc, /sortingLabel/);
  assert.doesNotMatch(chromeSrc, /Place a hold/);
  assert.equal(chromeSrc.includes(">Noted<"), false);
  assert.equal(chromeSrc.includes("Review bag"), false);
  assert.equal(chromeSrc.includes("bag-glyph"), false);
  assert.equal(chromeSrc.includes("review-bag"), false);
  assert.equal(chromeSrc.includes("LampMark"), false);
  assert.match(chromeSrc, /user\.role === "owner" \|\| user\.role === "op"/);
});

test("account menu holds theme, People, Maintain, and Settings", () => {
  assert.match(menuSrc, /profile-theme-section/);
  assert.doesNotMatch(menuSrc, /profile-ambient-section/);
  assert.doesNotMatch(menuSrc, /Room wash/);
  assert.match(menuSrc, />\s*People\s*</);
  assert.match(menuSrc, />\s*Maintain\s*</);
  assert.match(menuSrc, />\s*Settings\s*</);
  assert.match(menuSrc, />\s*Downloads\s*</);
  assert.match(menuSrc, />\s*Sorting\s*</);
  assert.equal(chromeSrc.includes("theme-toggle"), false);
  assert.equal(chromeSrc.includes("ambient-toggle"), false);
});

test("Library card text-size slider stays inside dismiss hit-testing", () => {
  assert.match(menuSrc, /pointerEventInsideNode/);
  assert.match(menuSrc, /profile-font-slider/);
  assert.match(menuSrc, /type="range"/);
  assert.match(menuSrc, /ui_font_step/);
  assert.match(menuSrc, /aria-label=\{`Library card \$\{user\.display_name\} \$\{roleLabel\}`\}/);
  assert.match(menuSrc, /Text size/);
});

test("topbar stacks above Hall so the Library card panel can receive clicks", () => {
  assert.match(stylesSrc, /\.room > \.topbar\s*\{[^}]*z-index:\s*200/s);
  assert.match(stylesSrc, /\.room > \*\s*\{[^}]*z-index:\s*1/s);
});

test("mobile tab bar is Hall, Search, Favorites, You, and Desk for keepers", () => {
  assert.match(chromeSrc, /mobile-tabbar/);
  assert.match(chromeSrc, />\s*Favorites\s*</);
  assert.match(chromeSrc, /DESK_TAB/);
  assert.match(chromeSrc, />\s*You\s*</);
  assert.match(chromeSrc, /to="\/card"/);
  assert.match(chromeSrc, /--tab-count/);
  assert.match(chromeSrc, /op \? 5 : 4/);
  assert.match(chromeSrc, /id="main"/);
  assert.match(chromeSrc, /SKIP_TO_CONTENT/);
  assert.match(chromeSrc, /skip-link/);
  assert.ok(chromeSrc.indexOf("skip-link") < chromeSrc.indexOf('className="topbar"'));
  assert.equal(chromeSrc.includes("bag-glyph"), false);
});

test("phone tab bar is fixed to the viewport and the skip link is first in chrome", () => {
  const loginSrc = readFileSync(join(root, "pages/LoginPage.jsx"), "utf8");
  assert.equal(loginSrc.includes("Skip to library"), false);
  assert.match(chromeSrc, /className="skip-link"/);
  assert.match(stylesSrc, /\.skip-link/);
  assert.match(stylesSrc, /\.room > \.mobile-tabbar\s*\{[^}]*position:\s*fixed/s);
  assert.match(stylesSrc, /\.room > \.mobile-tabbar\s*\{[^}]*bottom:\s*0/s);
  assert.match(stylesSrc, /minmax\(0,\s*1fr\)/);
  assert.match(stylesSrc, /env\(safe-area-inset-bottom,\s*0px\)/);
  assert.match(stylesSrc, /scroll-padding-bottom:\s*var\(--mobile-tabbar-clearance\)/);
  assert.match(stylesSrc, /padding-bottom:\s*var\(--mobile-tabbar-clearance\)/);
  assert.match(stylesSrc, /min-height:\s*44px/);
});

test("search slash hint hides on coarse pointers", () => {
  assert.match(stylesSrc, /@media \(pointer:\s*coarse\)[\s\S]*\.search-field kbd[\s\S]*display:\s*none/);
});

test("/browse is the stacks room and /find redirects to Search", () => {
  assert.match(mainSrc, /path="browse" element=\{<BrowsePage/);
  assert.equal(mainSrc.includes("BrowseToHall"), false);
  assert.match(mainSrc, /function FindToSearch/);
  assert.match(mainSrc, /path="find" element=\{<FindToSearch/);
  assert.match(mainSrc, /pathname: "\/search"/);
  assert.match(mainSrc, /path="card"/);
});
