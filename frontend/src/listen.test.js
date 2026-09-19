import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  canListenInApp,
  chapterAt,
  decodeListenPosition,
  encodeListenPosition,
  formatListenClock,
  listenFraction,
  nextChapter,
  prevChapter,
  workListenPath,
} from "./listen.js";

describe("audiobook Listen helpers", () => {
  it("opens Listen only for on-disk audiobook audio", () => {
    assert.equal(canListenInApp({ kind: "audiobook" }, [{ filename: "Dune.m4b" }], true), true);
    assert.equal(canListenInApp({ kind: "audiobook" }, [{ filename: "Dune.m4b" }], false), false);
    assert.equal(canListenInApp({ kind: "book" }, [{ filename: "Dune.m4b" }], true), false);
    assert.equal(
      canListenInApp({ kind: "audiobook" }, [{ filename: "notes.pdf" }, { filename: "cover.jpg" }], true),
      false,
    );
    assert.equal(
      canListenInApp({ kind: "audiobook" }, [{ filename: "ghost.m4b", on_disk: false }], true),
      false,
    );
  });

  it("deep-links peek Listen onto the work page player", () => {
    assert.equal(workListenPath("abc"), "/works/abc?listen=1");
    assert.equal(workListenPath("abc", "f2"), "/works/abc?listen=1&file=f2");
  });

  it("round-trips listen bookmarks and overall fraction", () => {
    const encoded = encodeListenPosition("f1", 12.5);
    assert.deepEqual(decodeListenPosition(encoded), { fileId: "f1", seconds: 12.5 });
    assert.deepEqual(decodeListenPosition("f1:9"), { fileId: "f1", seconds: 9 });
    assert.equal(listenFraction({ fileIndex: 1, fileCount: 4, localFraction: 0.5 }), 0.375);
  });

  it("finds chapter neighbors for Media Session skip", () => {
    const chapters = [
      { title: "Prologue", start: 0 },
      { title: "One", start: 100 },
      { title: "Two", start: 250 },
    ];
    assert.equal(chapterAt(chapters, 120)?.title, "One");
    assert.equal(nextChapter(chapters, 120)?.title, "Two");
    // Mid-chapter skip-back restarts the current chapter.
    assert.equal(prevChapter(chapters, 120)?.title, "One");
    assert.equal(prevChapter(chapters, 100.5)?.title, "Prologue");
    assert.equal(formatListenClock(3661), "1:01:01");
  });
});
