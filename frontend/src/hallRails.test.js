import assert from "node:assert/strict";
import { test } from "node:test";
import { continueRailItems, notedRailItems } from "./hallRails.js";

test("a continue rail is omitted when it has no items", () => {
  assert.equal(continueRailItems(undefined), null);
  assert.equal(continueRailItems(null), null);
  assert.equal(continueRailItems([]), null);
  const kept = [{ id: "1", title: "Dune" }];
  assert.equal(continueRailItems(kept), kept);
});

test("New & noted is omitted when the lanes have no titles", () => {
  assert.equal(notedRailItems(null), null);
  assert.equal(notedRailItems({ lanes: [] }), null);
  assert.equal(notedRailItems({ lanes: [{ items: [{ title: "  " }] }] }), null);
  const items = notedRailItems({
    lanes: [
      {
        items: [
          { title: "Dune", author: "Frank Herbert", isbn: "9780441172719", shelved: { id: "book-1" } },
          { title: "Dune", author: "Frank Herbert", isbn: "9780441172719" },
        ],
      },
    ],
  });
  assert.equal(items.length, 1);
  assert.equal(items[0].title, "Dune");
  assert.equal(items[0].href, "/works/book-1");
});
