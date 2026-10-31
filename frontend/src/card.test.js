import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "vitest";

const root = dirname(fileURLToPath(import.meta.url));
const cardSrc = readFileSync(join(root, "pages/CardPage.jsx"), "utf8");
const menuSrc = readFileSync(join(root, "components/ProfileMenu.jsx"), "utf8");
const notesSrc = readFileSync(join(root, "pages/NotificationsPage.jsx"), "utf8");
const mainSrc = readFileSync(join(root, "main.jsx"), "utf8");

test("Library card gathers continue, finished, favorites, and Wanted", () => {
  assert.match(cardSrc, /Your library/);
  assert.match(cardSrc, /Library card/);
  assert.match(cardSrc, /title="Continue reading"/);
  assert.match(cardSrc, /title="Continue listening"/);
  assert.match(cardSrc, /title="Recently finished"/);
  assert.match(cardSrc, /title="Favorites"/);
  assert.match(cardSrc, /to="\/wanted"/);
  assert.match(cardSrc, /wanted_count/);
  assert.match(cardSrc, /YOUR_ASKS/);
  assert.match(cardSrc, /your-asks/);
  assert.equal(cardSrc.includes("due date"), false);
  assert.equal(cardSrc.includes("Borrow"), false);
  assert.match(mainSrc, /path="card"/);
  assert.match(menuSrc, /to="\/card"/);
  assert.match(menuSrc, /Your library/);
  assert.match(notesSrc, /Library card/);
  assert.equal(notesSrc.includes(">Profile<"), false);
});
