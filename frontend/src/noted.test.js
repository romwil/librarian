import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "vitest";

import {
  collapseNotedBooks,
  listFormatActions,
  notedFindHref,
  notedFormatActions,
  notedSearchHref,
  notedWantedBody,
  weekCountLabel,
} from "./noted.js";

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

test("a list card keeps the shelved book and omits the missing audiobook", () => {
  const item = {
    kind: "book",
    title: "Atomic Habits",
    author: "James Clear",
    shelved: { id: "book-atomic", title: "Atomic Habits" },
    shelved_audiobook: null,
  };
  const actions = listFormatActions(item);
  assert.equal(actions.length, 1);
  const book = actions[0];
  assert.equal(book.kind, "book");
  assert.equal(book.owned, true);
  assert.equal(book.label, "On the shelf");
  assert.equal(book.href, "/works/book-atomic");
  assert.equal(book.listenHref, "");
  assert.equal(book.readHref, "/works/book-atomic?read=1");
  assert.equal(book.downloadHref, "/api/works/book-atomic/download");
  assert.equal(
    actions.some((action) => action.kind === "audiobook" || /audiobook/i.test(action.label)),
    false,
  );

  const pair = notedFormatActions(item);
  assert.equal(pair.find((action) => action.kind === "audiobook").label, "Add to Wanted · audiobook");
  assert.equal(listFormatActions({ ...item, kind: "audiobook" }).map((action) => action.kind).join(","), "audiobook");

  const both = listFormatActions({
    kind: "book",
    shelved: { id: "book-1" },
    shelved_audiobook: { id: "audio-1" },
  });
  assert.deepEqual(
    both.map((action) => action.kind),
    ["book"],
  );
  assert.equal(both[0].readHref, "/works/book-1?read=1");
  assert.equal(both[0].downloadHref, "/api/works/book-1/download");
  assert.equal(both[0].listenHref, "");
});

test("Search keeps one New & noted door", () => {
  assert.match(searchSrc, /noted-door/);
  assert.match(searchSrc, /New & noted/);
  assert.equal((searchSrc.match(/to="\/noted"/g) || []).length, 1);
  assert.equal(searchSrc.includes("TRENDING_BOOKS_LABEL"), false);
  assert.equal(searchSrc.includes("Trending books"), false);
  assert.match(searchSrc, /discover-panel/);
  assert.match(searchSrc, /On the shelf/);
});

test("duplicate list rows collapse to one book and a week count", () => {
  const books = collapseNotedBooks([
    {
      title: "The Correspondent",
      author: "Virginia Evans",
      isbn13: "978-0-593-44095-5",
      weeks: ["2026-08-30", "2026-09-06", "2026-09-13", "2026-09-20", "2026-09-27", "2026-10-04"],
      status: "missing",
    },
    {
      title: " the correspondent ",
      author: "virginia evans",
      isbn13: "9780593440962",
      weeks: ["2026-08-30", "2026-09-06"],
      status: "missing",
    },
    {
      title: "The Correspondent",
      author: "Someone Else",
      isbn13: "9781111111111",
      weeks: ["2026-10-04"],
      status: "missing",
    },
    {
      title: "Buckeye",
      author: "Patrick Ryan",
      weeks: ["2026-10-04"],
      status: "matched",
      work_id: "work-buckeye",
    },
  ]);
  assert.equal(books.length, 3);
  const correspondent = books.find((book) => book.author === "Virginia Evans");
  assert.ok(correspondent);
  assert.equal(correspondent.weekCount, 6);
  assert.equal(correspondent.weeks, undefined);
  assert.equal(weekCountLabel(correspondent.weekCount), "6 weeks");
  assert.equal(weekCountLabel(1), "");
  assert.equal(books.filter((book) => book.title === "Buckeye")[0].status, "matched");
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
  assert.match(pageSrc, /listFormatActions/);
  assert.equal(pageSrc.includes("companion_note"), false);
  assert.equal(pageSrc.includes("noted-companion"), false);
  assert.match(pageSrc, /noted-shelf-\$\{action\.kind\}/);
  assert.match(pageSrc, /noted-want-\$\{action\.kind\}/);
  assert.match(pageSrc, /api\.addWanted/);
  assert.equal(pageSrc.toLowerCase().includes("sabnzbd"), false);
  assert.equal(pageSrc.toLowerCase().includes("audible"), false);
  assert.equal(pageSrc.toLowerCase().includes("libby"), false);
  assert.equal(pageSrc.toLowerCase().includes("goodreads"), false);
});
