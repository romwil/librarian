import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { clothFor, coverCaption, isSquareKind, jobChipLabel, shouldOpenPeek } from "./cover.js";

describe("reading room cover helpers", () => {
  it("picks a stable cloth color from the title", () => {
    assert.equal(clothFor("Piranesi"), clothFor("Piranesi"));
    assert.notEqual(clothFor("Piranesi"), clothFor("Circe"));
  });

  it("opens peek on a plain click and not a modifier click", () => {
    assert.equal(shouldOpenPeek({ metaKey: false, ctrlKey: false, shiftKey: false, altKey: false }), true);
    assert.equal(shouldOpenPeek({ metaKey: true, ctrlKey: false, shiftKey: false, altKey: false }), false);
  });

  it("uses square covers for listening kinds only", () => {
    assert.equal(isSquareKind("audiobook"), true);
    assert.equal(isSquareKind("music"), true);
    assert.equal(isSquareKind("book"), false);
    assert.equal(isSquareKind("comic"), false);
  });

  it("labels living request chips", () => {
    assert.equal(jobChipLabel(undefined, "reader"), "Ask the house");
    assert.equal(jobChipLabel(undefined, "owner"), "Request");
    assert.equal(jobChipLabel("asked"), "Asked");
    assert.equal(jobChipLabel("organized"), "Open");
  });

  it("uses issue dates and numbers as gilt captions", () => {
    assert.equal(coverCaption({ kind: "magazine", series_index: "2026-09", title: "The Atlantic" }), "2026-09");
    assert.equal(coverCaption({ kind: "comic", series_name: "Saga", series_index: "54" }), "Saga #54");
    assert.equal(coverCaption({ kind: "book", title: "Piranesi" }), "Piranesi");
  });
});
