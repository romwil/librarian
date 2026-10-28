import assert from "node:assert/strict";
import { describe, it } from "vitest";
import { bookAvailability, catalogStatus, forListCard } from "./availability.js";

const book = {
  id: "book-1",
  kind: "book",
  title: "Circe",
  author: "Madeline Miller",
  isbn: "9780316556347",
};

const miss = {
  applicable: true,
  shelved: null,
  find: { kind: "audiobook", title: "Circe", author: "Madeline Miller", isbn: "9780316556347" },
};

describe("availability chip", () => {
  it("offers Listen when the companion audiobook is on the shelf", () => {
    const view = bookAvailability({
      work: book,
      audiobook: {
        applicable: true,
        shelved: { id: "audio-1", title: "Circe" },
        find: miss.find,
      },
      role: "reader",
    });
    assert.equal(view.verb, "listen");
    assert.equal(view.chip, "Listen");
    assert.equal(view.listenHref, "/works/audio-1?listen=1");
    assert.equal(view.readHref, "/works/book-1?read=1");
    assert.equal(view.downloadHref, "/api/works/book-1/download");
    assert.equal(view.canAdd, false);
    assert.equal(view.searchHref, "");
  });

  it("says the audiobook is wanted and keeps search and find for a miss", () => {
    const view = bookAvailability({ work: book, audiobook: miss, role: "reader" });
    assert.equal(view.verb, "want");
    assert.equal(view.chip, "Wanted");
    assert.equal(view.note, "The audiobook is wanted");
    assert.match(view.searchHref, /\/search\?/);
    assert.match(view.searchHref, /kind=audiobook/);
    assert.match(view.searchHref, /title=Circe/);
    assert.match(view.findHref, /\/search\?/);
    assert.match(view.findHref, /kind=audiobook/);
    assert.equal(view.downloadHref, "/api/works/book-1/download");
    assert.equal(view.canAdd, false);
    assert.equal(view.canDismiss, false);
    assert.equal(forListCard(view).show, false);
  });

  it("keeps a shelved Listen link on a list card and drops only the missing format", () => {
    const listen = bookAvailability({
      work: book,
      audiobook: {
        applicable: true,
        shelved: { id: "audio-1", title: "Circe" },
        find: miss.find,
      },
      role: "reader",
    });
    assert.equal(forListCard(listen).verb, "listen");
    const wanted = bookAvailability({ work: book, audiobook: miss, role: "owner" });
    assert.equal(wanted.note, "The audiobook is wanted");
    assert.equal(wanted.canAdd, true);
    assert.equal(forListCard(wanted).show, false);
  });

  it("lets an owner add when no row exists, and dismiss an open row", () => {
    const open = bookAvailability({ work: book, audiobook: miss, role: "owner" });
    assert.equal(open.canAdd, true);
    assert.equal(open.addBody.kind, "audiobook");
    assert.equal(open.addBody.work_id, "book-1");

    const asked = bookAvailability({
      work: book,
      audiobook: miss,
      wanted: { id: "w1", status: "asked", kind: "audiobook" },
      role: "op",
    });
    assert.equal(asked.canAdd, false);
    assert.equal(asked.canDismiss, true);
    assert.equal(asked.wantedId, "w1");
    assert.equal(asked.note, "Asked");
  });

  it("hides Wanted after the house dismisses the audiobook", () => {
    const view = bookAvailability({
      work: book,
      audiobook: miss,
      wanted: { id: "w1", status: "dismissed" },
      role: "owner",
    });
    assert.equal(view.verb, "read");
    assert.equal(view.chip, "Read");
    assert.equal(view.canAdd, false);
    assert.equal(view.canDismiss, false);
  });

  it("stays quiet for comics and for titles beyond the shelves", () => {
    assert.equal(bookAvailability({ work: { ...book, kind: "comic" }, audiobook: miss }).show, false);
    assert.equal(bookAvailability({ work: book, audiobook: miss, beyond: true }).show, false);
  });
});

describe("catalog status", () => {
  it("says Read on the shelf and Listen for audiobooks", () => {
    const print = catalogStatus({ work: book, role: "reader" });
    assert.equal(print.status, "On the shelf");
    assert.equal(print.verb, "Read");
    assert.equal(print.readHref, "/works/book-1?read=1");
    const audio = catalogStatus({ work: { ...book, kind: "audiobook" }, role: "reader" });
    assert.equal(audio.verb, "Listen");
    assert.equal(audio.listenHref, "/works/book-1?listen=1");
  });

  it("offers Get to keepers and Ask the house to readers when beyond", () => {
    const owner = catalogStatus({ work: { title: "Dune", kind: "book" }, role: "owner", beyond: true });
    assert.equal(owner.status, "Not on the shelf");
    assert.equal(owner.verb, "Get");
    assert.equal(owner.canAdd, true);
    const reader = catalogStatus({ work: { title: "Dune", kind: "book" }, role: "reader", beyond: true });
    assert.equal(reader.verb, "Ask the house");
    assert.equal(reader.canAdd, false);
  });

  it("turns a saved Usenet pick into Queued or Asked", () => {
    const asked = catalogStatus({
      work: { title: "Dune", kind: "book", job_status: "asked" },
      role: "owner",
      beyond: true,
    });
    assert.equal(asked.status, "Asked");
    assert.equal(asked.verb, "Queued");
    assert.equal(asked.canAdd, false);
    const saved = catalogStatus({
      work: { title: "Dune", kind: "book", wanted: { id: "w1", status: "wanted" } },
      role: "op",
      beyond: true,
    });
    assert.equal(saved.status, "Queued");
    assert.equal(saved.verb, "Queued");
    assert.equal(saved.canAdd, false);
  });

  it("names Asked, On the way, and Needs you", () => {
    assert.equal(catalogStatus({ work: { ...book, job_status: "asked" } }).status, "Asked");
    assert.equal(catalogStatus({ work: { ...book, job_status: "queued" } }).status, "On the way");
    assert.equal(catalogStatus({ work: { ...book, review_state: "needs_review" } }).status, "Needs you");
    assert.equal(catalogStatus({ work: { ...book, review_state: "needs_review" } }).verb, "");
  });
});
