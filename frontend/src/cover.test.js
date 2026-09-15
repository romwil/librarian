import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  clothFor,
  coverCaption,
  coverClassNames,
  coverOverlay,
  coverShapeClass,
  isLandscapeKind,
  isSquareKind,
  jobChipLabel,
  shouldOpenPeek,
} from "./cover.js";

describe("reading room cover helpers", () => {
  it("picks a stable cloth color from the title", () => {
    assert.equal(clothFor("Piranesi"), clothFor("Piranesi"));
    assert.notEqual(clothFor("Piranesi"), clothFor("Circe"));
  });

  it("opens peek on a plain click and not a modifier click", () => {
    assert.equal(shouldOpenPeek({ metaKey: false, ctrlKey: false, shiftKey: false, altKey: false }), true);
    assert.equal(shouldOpenPeek({ metaKey: true, ctrlKey: false, shiftKey: false, altKey: false }), false);
  });

  it("skins kinds with different shapes", () => {
    assert.equal(isSquareKind("music"), true);
    assert.equal(isSquareKind("audiobook"), false);
    assert.equal(isLandscapeKind("audiobook"), true);
    assert.equal(isSquareKind("book"), false);
    assert.equal(isSquareKind("comic"), false);
    assert.equal(coverShapeClass("book"), "is-portrait");
    assert.equal(coverShapeClass("magazine"), "is-magazine");
    assert.equal(coverShapeClass("comic"), "is-comic");
    assert.equal(coverShapeClass("audiobook"), "is-landscape");
    assert.equal(coverShapeClass("music"), "is-square");
    assert.match(coverClassNames({ kind: "book", title: "Dune" }), /cover-book is-portrait/);
    assert.match(coverClassNames({ kind: "music", music_state: "incoming" }), /is-incoming/);
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
    assert.equal(coverCaption({ kind: "music", title: "Dummy", music_state: "incoming" }), "Dummy · incoming");
  });

  it("puts magazine masthead and comic numbers in the overlay, not a book spine", () => {
    assert.equal(coverOverlay({ kind: "magazine", title: "The Atlantic", series_index: "2026-09" }).chip, "2026-09");
    assert.equal(coverOverlay({ kind: "comic", series_name: "Saga", series_index: "54", title: "Saga" }).chip, "#54");
    assert.equal(coverOverlay({ kind: "audiobook", title: "Dune", duration: "21h" }).chip, "21h");
    assert.equal(coverOverlay({ kind: "music", title: "Dummy", music_state: "incoming" }).chip, "Incoming");
    assert.equal(coverOverlay({ kind: "book", title: "Piranesi", author: "Clarke" }).byline, "Clarke");
  });
});
