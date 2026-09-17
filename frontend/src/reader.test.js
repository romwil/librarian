import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  canOpenInlineMedia,
  canReadInApp,
  filenameFromDisposition,
  primaryReadingFile,
  readerEngine,
  readerOpenError,
  readingFileName,
  workReaderPath,
} from "./reader.js";

describe("in-app reader", () => {
  it("opens EPUB, CBZ, and magazine PDF on the work page — not Calibre-web", () => {
    assert.equal(canReadInApp({ kind: "book" }, [{ filename: "Dune.epub" }]), true);
    assert.equal(canReadInApp({ kind: "comic" }, [{ filename: "Saga #54.cbz" }]), true);
    assert.equal(canReadInApp({ kind: "magazine" }, [{ filename: "Linux Magazine 2026-10.pdf" }]), true);
    assert.equal(readerEngine([{ filename: "Dune.epub" }]), "epub");
    assert.equal(readerEngine([{ filename: "Saga #54.cbz" }]), "cbz");
    assert.equal(readerEngine([{ filename: "issue.pdf" }]), "pdf");
  });

  it("prefers the payload over a cover still, and EPUB over a sibling PDF", () => {
    const files = [{ filename: "cover.jpg" }, { filename: "issue.pdf" }, { filename: "issue.epub" }];
    assert.equal(primaryReadingFile(files).filename, "issue.epub");
    assert.equal(readerEngine(files), "epub");
    assert.equal(canReadInApp({ kind: "magazine" }, files), true);
  });

  it("prefers the Reading Room badge and ignores missing DB paths", () => {
    const files = [
      { filename: "ghost.epub", on_disk: false },
      { filename: "Title.azw3", on_disk: true },
      { filename: "Title.epub", on_disk: true, reading_room: true },
    ];
    assert.equal(primaryReadingFile(files).filename, "Title.epub");
    assert.equal(canReadInApp({ kind: "book" }, files), true);
    assert.equal(
      canReadInApp({ kind: "book" }, [
        { filename: "ghost.epub", on_disk: false },
        { filename: "Title.azw3", on_disk: true },
      ]),
      false,
    );
  });

  it("does not steal Open for music or audiobooks (Phase 2b still owns playback)", () => {
    assert.equal(canReadInApp({ kind: "music" }, [{ filename: "01-track.flac" }]), false);
    assert.equal(canReadInApp({ kind: "audiobook" }, [{ filename: "Dune.m4b" }]), false);
    assert.equal(canReadInApp({ kind: "book" }, [{ filename: "cover.jpg" }]), false);
    assert.equal(canReadInApp({ kind: "book" }, []), false);
    assert.equal(canReadInApp({ kind: "book" }, [{ filename: "Title.azw3" }]), false);
  });

  it("Kindle-only books get Download, not inline Open", () => {
    assert.equal(canOpenInlineMedia({ kind: "book" }, true, false), false);
    assert.equal(canOpenInlineMedia({ kind: "music" }, true, false), true);
  });

  it("maps Foliate container failures to honest copy", () => {
    assert.match(readerOpenError(new Error("Failed to load container file")), /damaged|readable/);
    assert.equal(readerOpenError(new Error("nope"), 422), "This file isn’t a readable EPUB, CBZ, or PDF.");
  });

  it("deep-links peek Open onto the work page reader", () => {
    assert.equal(workReaderPath("abc"), "/works/abc?read=1");
    assert.equal(readingFileName([{ filename: "Piranesi.epub" }]), "Piranesi.epub");
    assert.equal(
      filenameFromDisposition('attachment; filename="Saga #54.cbz"', "volume"),
      "Saga #54.cbz",
    );
  });
});
