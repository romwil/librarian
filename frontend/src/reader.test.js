import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  canOpenInlineMedia,
  canReadInApp,
  chooseReadingFile,
  EPUB_PAGE_SURFACE,
  EPUB_READER_STYLES,
  filenameFromDisposition,
  pageTurnSide,
  primaryReadingFile,
  readerCtaLabel,
  readerEngine,
  readerOpenError,
  readingFileName,
  workDownloadUrl,
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

  it("chooses a specific magazine volume when every PDF is Reading Room", () => {
    const files = [
      { id: "v1", filename: "The Hacker Digest - Volume 01.pdf", reading_room: true },
      { id: "v2", filename: "The Hacker Digest - Volume 02.pdf", reading_room: true },
      { id: "cover", filename: "cover.jpg" },
    ];
    assert.equal(primaryReadingFile(files).filename, "The Hacker Digest - Volume 01.pdf");
    assert.equal(chooseReadingFile(files, "v2").filename, "The Hacker Digest - Volume 02.pdf");
    assert.equal(readerEngine(files, "v2"), "pdf");
    assert.equal(readingFileName(files, "", "v2"), "The Hacker Digest - Volume 02.pdf");
    assert.equal(workReaderPath("abc", "v2"), "/works/abc?read=1&file=v2");
    assert.equal(
      workDownloadUrl("abc", { inline: true, fileId: "v2" }),
      "/api/works/abc/download?inline=1&file=v2",
    );
  });

  it("does not steal Read for music or audiobooks (Listen owns audiobook playback)", () => {
    assert.equal(canReadInApp({ kind: "music" }, [{ filename: "01-track.flac" }]), false);
    assert.equal(canReadInApp({ kind: "audiobook" }, [{ filename: "Dune.m4b" }]), false);
    assert.equal(canOpenInlineMedia({ kind: "audiobook" }, true, false), false);
    assert.equal(canReadInApp({ kind: "book" }, [{ filename: "cover.jpg" }]), false);
    assert.equal(canReadInApp({ kind: "book" }, []), false);
    assert.equal(canReadInApp({ kind: "book" }, [{ filename: "Title.azw3" }]), false);
  });

  it("labels the in-browser reader CTA Read for books and comics", () => {
    assert.equal(readerCtaLabel({ kind: "book" }), "Read");
    assert.equal(readerCtaLabel({ kind: "comic" }), "Read");
    assert.equal(readerCtaLabel({ kind: "magazine" }), "Read");
    assert.equal(readerCtaLabel({ kind: "audiobook" }), "");
    assert.equal(readerCtaLabel({ kind: "music" }), "");
  });

  it("Kindle-only books get Download, not inline Read", () => {
    assert.equal(canOpenInlineMedia({ kind: "book" }, true, false), false);
    assert.equal(canOpenInlineMedia({ kind: "music" }, true, false), true);
  });

  it("maps Foliate container failures to honest copy", () => {
    assert.match(readerOpenError(new Error("Failed to load container file")), /damaged|readable/);
    assert.equal(readerOpenError(new Error("nope"), 422), "This file isn’t a readable EPUB, CBZ, or PDF.");
  });

  it("deep-links peek Open onto the work page reader", () => {
    assert.equal(workReaderPath("abc"), "/works/abc?read=1");
    assert.equal(workReaderPath("abc", "epub-1"), "/works/abc?read=1&file=epub-1");
    assert.equal(readingFileName([{ filename: "Piranesi.epub" }]), "Piranesi.epub");
    assert.equal(
      filenameFromDisposition('attachment; filename="Saga #54.cbz"', "volume"),
      "Saga #54.cbz",
    );
  });

  it("forces a light Foliate page so dark Reading Room chrome cannot dim text", () => {
    assert.match(EPUB_READER_STYLES, /color-scheme:\s*only light/);
    assert.match(EPUB_READER_STYLES, /--theme-bg-color:\s*#faf6ee/);
    assert.equal(EPUB_PAGE_SURFACE, "#faf6ee");
  });

  it("maps cover / page clicks to left and right turn zones", () => {
    assert.equal(pageTurnSide(10, 300), "left");
    assert.equal(pageTurnSide(290, 300), "right");
    assert.equal(pageTurnSide(150, 300), "");
    assert.equal(pageTurnSide(0, 0), "");
  });
});
