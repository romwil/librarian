import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { applyBodyFromDraft, fieldsFromWork, reviewReasonCopy } from "./review.js";

describe("review identify form", () => {
  it("explains no_payload instead of hiding identity fields", () => {
    const copy = reviewReasonCopy("no_payload");
    assert.match(copy, /cannot invent/);
    assert.match(copy, /complete root|Skip/);
  });

  it("prefills folder from SAB storage when work.folder_path is empty", () => {
    const fields = fieldsFromWork({
      title: "Christine",
      author: "Stephen King",
      kind: "book",
      folder_path: null,
      storage_path: "/downloads/books/Christine - Stephen King/Christine - Stephen King.epub",
    });
    assert.equal(fields.title, "Christine");
    assert.match(fields.folder, /Christine - Stephen King\.epub$/);
  });

  it("posts identity fields including folder", () => {
    const body = applyBodyFromDraft({
      title: "The Return of the King",
      author: "J. R. R. Tolkien",
      kind: "audiobook",
      isbn: "",
      series_name: "",
      series_index: "",
      year: "1955",
      folder: "/data/complete/Return",
    });
    assert.equal(body.kind, "audiobook");
    assert.equal(body.year, 1955);
    assert.equal(body.folder, "/data/complete/Return");
  });
});
