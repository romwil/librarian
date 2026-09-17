import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  applyBodyFromDraft,
  collisionActionCopy,
  collisionApplyAllowed,
  collisionDraftUnchanged,
  fieldsFromWork,
  queueReviewReasonCopy,
  reviewReasonCopy,
} from "./review.js";

describe("review identify form", () => {
  it("explains no_payload instead of hiding identity fields", () => {
    const copy = reviewReasonCopy("no_payload");
    assert.match(copy, /cannot invent/);
    assert.match(copy, /complete root|Skip/);
  });

  it("explains collision Skip vs Apply without overwrite", () => {
    const copy = reviewReasonCopy("collision");
    assert.match(copy, /[Cc]ollision/);
    assert.match(copy, /will not silent-overwrite|will not overwrite/i);
    assert.match(collisionActionCopy(), /Skip keeps/);
    assert.match(collisionActionCopy(), /will not overwrite/i);
  });

  it("blocks Apply on collision until identity or folder changes", () => {
    const work = {
      title: "To the Edge",
      author: "Cindy Gerard",
      kind: "book",
      isbn: "9780312990916",
      series_name: "Bodyguards",
      series_index: "1",
      folder_path: "/data/media/books/Cindy Gerard/To the Edge (1216)",
    };
    const draft = fieldsFromWork(work);
    assert.equal(collisionDraftUnchanged(draft, work), true);
    assert.equal(collisionApplyAllowed("collision", draft, work), false);
    assert.equal(collisionApplyAllowed("collision", { ...draft, title: "To the Edge (alt)" }, work), true);
    assert.equal(collisionApplyAllowed("unknown_identity", draft, work), true);
  });

  it("shortens review reasons for Queue Needs you cards", () => {
    assert.match(queueReviewReasonCopy("extra_files"), /Extra files/);
    assert.match(queueReviewReasonCopy("collision"), /Open Review/i);
    assert.match(queueReviewReasonCopy("collision"), /shelf/i);
    assert.match(queueReviewReasonCopy(""), /Waiting in Review/);
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
