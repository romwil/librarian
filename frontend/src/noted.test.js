import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "vitest";

import { notedFindHref, notedFormatActions, notedSearchHref, notedWantedBody } from "./noted.js";

const root = dirname(fileURLToPath(import.meta.url));
const pageSrc = readFileSync(join(root, "pages/NotedPage.jsx"), "utf8");
const searchSrc = readFileSync(join(root, "pages/SearchPage.jsx"), "utf8");
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
  assert.match(notedFindHref(card), /^\/search\?/);
  assert.match(notedFindHref(card), /kind=book/);
  assert.deepEqual(notedWantedBody(card, "audiobook"), {
    title: "Dune",
    author: "Frank Herbert",
    isbn: "9780441172719",
    kind: "audiobook",
  });
  assert.equal(notedWantedBody(card, "book").kind, "book");
});

test("a shelved format becomes On the shelf and the missing format stays Wanted", () => {
  const actions = notedFormatActions({
    title: "Atomic Habits",
    author: "James Clear",
    shelved: { id: "book-atomic", title: "Atomic Habits" },
    shelved_audiobook: null,
  });
  const book = actions.find((action) => action.kind === "book");
  const audio = actions.find((action) => action.kind === "audiobook");
  assert.equal(book.owned, true);
  assert.equal(book.label, "On the shelf");
  assert.equal(book.href, "/works/book-atomic");
  assert.equal(book.listenHref, "");
  assert.equal(book.readHref, "/works/book-atomic?read=1");
  assert.equal(book.downloadHref, "/api/works/book-atomic/download");
  assert.equal(audio.owned, false);
  assert.equal(audio.label, "Add to Wanted · audiobook");
  assert.equal(audio.readHref, "");
  assert.equal(audio.downloadHref, "");

  const both = notedFormatActions({
    shelved: { id: "book-1" },
    shelved_audiobook: { id: "audio-1" },
  });
  const ownedAudio = both.find((action) => action.kind === "audiobook");
  assert.equal(ownedAudio.owned, true);
  assert.equal(ownedAudio.label, "On the shelf");
  assert.equal(ownedAudio.href, "/works/audio-1");
  assert.match(ownedAudio.listenHref, /\/works\/audio-1\?listen=1/);
  assert.equal(ownedAudio.readHref, "");
  assert.equal(ownedAudio.downloadHref, "");
  const ownedBook = both.find((action) => action.kind === "book");
  assert.equal(ownedBook.readHref, "/works/book-1?read=1");
  assert.equal(ownedBook.downloadHref, "/api/works/book-1/download");
});

test("Search keeps a Trending books door to New & noted", () => {
  assert.match(searchSrc, /trending-books-door/);
  assert.match(searchSrc, /TRENDING_BOOKS_LABEL/);
  assert.match(searchSrc, /to="\/noted"/);
  assert.match(searchSrc, /discover-panel/);
  assert.match(searchSrc, /On the shelf/);
});

test("New & noted page searches, finds, and adds to Wanted", () => {
  assert.match(mainSrc, /path="noted"/);
  assert.match(pageSrc, /New & noted/);
  assert.match(pageSrc, /Search the shelves/);
  assert.match(pageSrc, /Find beyond/);
  assert.match(pageSrc, /Add to Wanted/);
  assert.match(pageSrc, /On the shelf/);
  assert.match(pageSrc, />\s*Read\s*</);
  assert.match(pageSrc, />\s*Download\s*</);
  assert.match(pageSrc, /noted-read-\$\{action\.kind\}/);
  assert.match(pageSrc, /noted-download-\$\{action\.kind\}/);
  assert.match(pageSrc, /notedFormatActions/);
  assert.match(pageSrc, /noted-shelf-\$\{action\.kind\}/);
  assert.match(pageSrc, /noted-want-\$\{action\.kind\}/);
  assert.match(pageSrc, /api\.addWanted/);
  assert.equal(pageSrc.toLowerCase().includes("sabnzbd"), false);
  assert.equal(pageSrc.toLowerCase().includes("audible"), false);
  assert.equal(pageSrc.toLowerCase().includes("libby"), false);
  assert.equal(pageSrc.toLowerCase().includes("goodreads"), false);
});
