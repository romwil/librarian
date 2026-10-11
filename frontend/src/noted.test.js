import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

import { notedFindHref, notedSearchHref, notedWantedBody } from "./noted.js";

const root = dirname(fileURLToPath(import.meta.url));
const pageSrc = readFileSync(join(root, "pages/NotedPage.jsx"), "utf8");
const mainSrc = readFileSync(join(root, "main.jsx"), "utf8");

const card = {
  title: "Dune",
  author: "Frank Herbert",
  isbn: "9780441172719",
  kind: "book",
  search: {
    q: "Frank Herbert Dune",
    kind: "book",
    title: "Dune",
    author: "Frank Herbert",
    isbn: "9780441172719",
  },
  find: {
    q: "Frank Herbert Dune",
    kind: "book",
    title: "Dune",
    author: "Frank Herbert",
    isbn: "9780441172719",
  },
  wanted: {
    title: "Dune",
    author: "Frank Herbert",
    isbn: "9780441172719",
    kind: "book",
    kinds: ["book", "audiobook"],
  },
};

test("noted cards link to search and find and build a Wanted body", () => {
  assert.match(notedSearchHref(card), /^\/search\?/);
  assert.match(notedSearchHref(card), /title=Dune/);
  assert.match(notedFindHref(card), /^\/find\?/);
  assert.match(notedFindHref(card), /kind=book/);
  assert.deepEqual(notedWantedBody(card, "audiobook"), {
    title: "Dune",
    author: "Frank Herbert",
    isbn: "9780441172719",
    kind: "audiobook",
  });
  assert.equal(notedWantedBody(card, "book").kind, "book");
});

test("New & noted page searches, finds, and adds to Wanted", () => {
  assert.match(mainSrc, /path="noted"/);
  assert.match(pageSrc, /New & noted/);
  assert.match(pageSrc, /Search the shelves/);
  assert.match(pageSrc, /Find beyond/);
  assert.match(pageSrc, /Add to Wanted/);
  assert.match(pageSrc, /noted-want-\$\{kind\}/);
  assert.match(pageSrc, /\["book", "audiobook"\]/);
  assert.match(pageSrc, /api\.addWanted/);
  assert.equal(pageSrc.toLowerCase().includes("sabnzbd"), false);
  assert.equal(pageSrc.toLowerCase().includes("audible"), false);
  assert.equal(pageSrc.toLowerCase().includes("libby"), false);
  assert.equal(pageSrc.toLowerCase().includes("goodreads"), false);
});
