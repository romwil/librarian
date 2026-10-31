import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { describe, it } from "vitest";
import { wantedDeskModel, wantedSearchStatus } from "./wantedDesk.js";

const items = [
  {
    id: "w-miss",
    work_id: "book-1",
    title: "Circe",
    author: "Madeline Miller",
    kind: "audiobook",
    status: "wanted",
  },
  {
    id: "w-hand",
    title: "Piranesi",
    author: "Susanna Clarke",
    kind: "book",
    status: "asked",
  },
  {
    id: "w-gone",
    title: "Dismissed",
    kind: "audiobook",
    status: "dismissed",
  },
];

describe("Wanted desk", () => {
  it("lists companion misses and hand-added titles, not dismissed rows", () => {
    const desk = wantedDeskModel({ items, role: "reader" });
    assert.deepEqual(
      desk.rows.map((row) => row.title),
      ["Circe", "Piranesi"],
    );
    assert.equal(desk.rows[0].workId, "book-1");
    assert.equal(desk.rows[0].statusLabel, "Wanted");
    assert.match(desk.rows[0].statusDetail, /Waiting for the next search/);
    assert.equal(desk.rows[1].statusLabel, "Asked");
    assert.match(desk.rows[1].statusDetail, /waiting for confirm/);
    assert.equal(desk.empty, false);
  });

  it("keeps add and dismiss with the owner and op", () => {
    const reader = wantedDeskModel({ items, role: "reader" });
    assert.equal(reader.canAdd, false);
    assert.equal(reader.rows.every((row) => row.canDismiss === false), true);

    const owner = wantedDeskModel({ items, role: "owner" });
    assert.equal(owner.canAdd, true);
    assert.equal(owner.rows[0].canDismiss, true);

    const op = wantedDeskModel({ items, role: "op" });
    assert.equal(op.canAdd, true);
    assert.equal(op.rows[1].canDismiss, true);
  });

  it("shows On the shelf for a format the house already has", () => {
    const desk = wantedDeskModel({
      role: "owner",
      items: [
        {
          id: "w-audio",
          title: "Any Other Name",
          author: "Craig Johnson",
          kind: "audiobook",
          status: "wanted",
          shelved_book: { id: "book-name", title: "Any Other Name" },
          shelved_audiobook: null,
        },
        {
          id: "w-owned-audio",
          title: "Atomic Habits",
          author: "James Clear",
          kind: "audiobook",
          status: "wanted",
          shelved_audiobook: { id: "audio-atomic" },
        },
      ],
    });
    assert.equal(desk.rows[0].bookShelf.label, "Book on the shelf");
    assert.equal(desk.rows[0].bookShelf.href, "/works/book-name");
    assert.equal(desk.rows[0].audioShelf, null);
    assert.equal(desk.rows[1].audioShelf.label, "On the shelf");
    assert.equal(desk.rows[1].audioShelf.href, "/works/audio-atomic");
    assert.match(desk.rows[1].audioShelf.listenHref, /listen=1/);
    assert.equal(desk.rows[1].bookShelf, null);
  });

  it("names Search all for the active type and keeps an empty selection quiet", () => {
    const all = wantedDeskModel({ items, role: "owner", kind: "", selectedCount: 0, total: 2 });
    assert.equal(all.toolbar.searchAllLabel, "Search all");
    assert.equal(all.toolbar.selectPageLabel, "Select page");
    assert.equal(all.toolbar.searchSelectedDisabled, true);

    const books = wantedDeskModel({ items, role: "owner", kind: "book", selectedCount: 1, total: 4 });
    assert.equal(books.toolbar.searchAllLabel, "Search all books");
    assert.equal(books.toolbar.searchSelectedLabel, "Search selected");
    assert.equal(books.toolbar.searchSelectedDisabled, false);

    const audio = wantedDeskModel({ items, role: "op", kind: "audiobook", total: 3 });
    assert.equal(audio.toolbar.searchAllLabel, "Search all audiobooks");
    const reader = wantedDeskModel({ items, role: "reader", kind: "book", total: 2 });
    assert.equal(reader.toolbar.canSearch, false);
    assert.equal(reader.toolbar.searchAllDisabled, true);
  });

  it("says when a wanted row will try again, and Searching while a request is open", () => {
    const waiting = wantedSearchStatus(
      { status: "wanted", next_search_at: 1_700_086_400 },
      { now: 1_700_000_000 },
    );
    assert.equal(waiting.label, "Wanted");
    assert.match(waiting.detail, /Waiting for the next search/);
    assert.match(waiting.retry, /Tries again/);

    const searching = wantedSearchStatus({ status: "wanted" }, { searching: true });
    assert.equal(searching.label, "Searching");
    const down = wantedSearchStatus({ status: "asked" }, { attempt: { downloader: true } });
    assert.match(down.detail, /downloader did not answer/);
    const paused = wantedSearchStatus({ status: "wanted" }, { attempt: { outcome: "rate_limited" } });
    assert.equal(paused.label, "Wanted");
    assert.match(paused.detail, /asked us to wait/);
  });

  it("does not offer Search the shelves, and Find beyond asks for hits on the row", () => {
    const source = readFileSync(new URL("./pages/WantedPage.jsx", import.meta.url), "utf8");
    assert.equal(source.includes("Search the shelves"), false);
    assert.equal(source.includes("/find"), false);
    assert.match(source, /Find beyond/);
    assert.match(source, /type="button"/);
    assert.match(source, /wantedBeyond/);
    assert.doesNotMatch(source, /findHref/);
  });

  it("is empty when nothing is still wanted", () => {
    const desk = wantedDeskModel({ items: [{ id: "x", title: "Gone", status: "dismissed" }], role: "owner" });
    assert.equal(desk.empty, true);
    assert.equal(desk.canAdd, true);
    assert.deepEqual(desk.rows, []);
  });
});
