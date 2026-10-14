import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  canOpenInlineMedia,
  canReadInApp,
  chooseReadingFile,
  EPUB_PAGE_SURFACE,
  EPUB_READER_STYLES,
  filenameFromDisposition,
  comicTurnSide,
  pageTurnSide,
  pageTurnTarget,
  primaryReadingFile,
  comicSpreadMode,
  readerChromeHint,
  readerFlow,
  turnReaderPage,
  readerWheelDelta,
  scrollReader,
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

  it("turns stage letterbox edges and image edges as different targets", () => {
    const stage = { left: 0, width: 900 };
    const image = { left: 300, width: 300 };
    assert.equal(pageTurnTarget(40, stage), "left");
    assert.equal(pageTurnTarget(860, stage), "right");
    assert.equal(pageTurnTarget(450, stage), "");
    assert.equal(pageTurnTarget(40, null), "");
    assert.equal(pageTurnTarget(40, { left: 0, width: 0 }), "");

    // The cover's left edge sits in the stage center. Viewport x against the
    // image width alone (as if the image started at x=0) points the wrong way.
    assert.equal(pageTurnSide(310, image.width), "right");
    assert.equal(pageTurnTarget(310, image), "left");
    assert.equal(pageTurnTarget(580, image), "right");
    assert.equal(pageTurnTarget(450, image), "");

    assert.equal(comicTurnSide(40, stage, image), "left");
    assert.equal(comicTurnSide(860, stage, image), "right");
    assert.equal(comicTurnSide(310, stage, image), "left");
    assert.equal(comicTurnSide(580, stage, image), "right");
    assert.equal(comicTurnSide(450, stage, image), "");
    assert.equal(comicTurnSide(450, stage, null), "");
  });

  it("scrolls reflowable prose and leaves comics, fixed-layout, and PDF on a page surface", () => {
    assert.equal(readerFlow("epub"), "scrolled");
    assert.equal(readerFlow("cbz"), "");
    assert.equal(readerFlow("cbz", true), "");
    assert.equal(readerFlow("epub", true), "");
    assert.equal(readerFlow("pdf"), "");
    assert.equal(readerFlow(""), "");
    assert.equal(readerChromeHint("epub"), "Scroll to read · edges or ← → turn · Esc closes");
    assert.equal(readerChromeHint("cbz"), "Edges or ← → turn · Esc closes");
  });

  it("turns a comic one page at a time from an edge tap or arrow", () => {
    const book = { rendition: { layout: "pre-paginated" } };
    comicSpreadMode(book);
    assert.equal(book.rendition.spread, "none");
    assert.equal(book.rendition.layout, "pre-paginated");
    assert.equal(comicSpreadMode(null), null);

    const view = {
      page: 0,
      goLeft() {
        this.page -= 1;
      },
      goRight() {
        this.page += 1;
      },
    };
    turnReaderPage(view, pageTurnSide(290, 300));
    assert.equal(view.page, 1);
    turnReaderPage(view, "right");
    assert.equal(view.page, 2);
    turnReaderPage(view, pageTurnSide(10, 300));
    assert.equal(view.page, 1);
    turnReaderPage(view, pageTurnSide(150, 300));
    assert.equal(view.page, 1);
    assert.equal(turnReaderPage(null, "right"), false);
  });

  it("turns wheel and trackpad ticks into pixels, and ignores pinch-zoom", () => {
    assert.equal(readerWheelDelta({ deltaY: 120, deltaX: 0, deltaMode: 0 }), 120);
    assert.equal(readerWheelDelta({ deltaY: 0, deltaX: -40, deltaMode: 0 }), -40);
    assert.equal(readerWheelDelta({ deltaY: 2, deltaMode: 1 }), 32);
    assert.equal(readerWheelDelta({ deltaY: 1, deltaMode: 2 }), 800);
    assert.equal(readerWheelDelta({ deltaY: 80, ctrlKey: true }), 0);
    assert.equal(readerWheelDelta(null), 0);
  });

  it("scrolls the open section and steps to the next spine item only at the edge", () => {
    const mid = { containerPosition: 400, start: 400, size: 700, viewSize: 4000, atEnd: false, atStart: false };
    assert.equal(scrollReader(mid, 80), true);
    assert.equal(mid.containerPosition, 480);

    const end = {
      containerPosition: 3300,
      start: 3300,
      size: 700,
      viewSize: 4000,
      atEnd: false,
      atStart: false,
      next() {
        this.stepped = "next";
      },
    };
    assert.equal(scrollReader(end, 40), true);
    assert.equal(end.stepped, "next");
    assert.equal(end.containerPosition, 3300);

    const done = { ...end, atEnd: true, stepped: "" };
    assert.equal(scrollReader(done, 40), false);

    const top = {
      containerPosition: 0,
      start: 0,
      size: 700,
      viewSize: 4000,
      atEnd: false,
      atStart: false,
      prev() {
        this.stepped = "prev";
      },
    };
    assert.equal(scrollReader(top, -30), true);
    assert.equal(top.stepped, "prev");
    assert.equal(scrollReader({ containerPosition: 10 }, 0), false);
  });
});
