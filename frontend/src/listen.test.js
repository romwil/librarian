import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  canListenInApp,
  chapterAt,
  chapterRemainingSeconds,
  decodeListenPosition,
  encodeListenPosition,
  formatListenClock,
  listenFraction,
  nextChapter,
  nextListenRate,
  nextSleepTimerId,
  prevChapter,
  shouldPersistListenCadence,
  shouldWriteListenProgress,
  sleepTimerLabel,
  splitContinueRails,
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
    const encoded = encodeListenPosition("f1", 12.5, { rate: 1.5 });
    assert.deepEqual(decodeListenPosition(encoded), { fileId: "f1", seconds: 12.5, rate: 1.5 });
    assert.deepEqual(decodeListenPosition("f1:9"), { fileId: "f1", seconds: 9, rate: 0 });
    assert.equal(listenFraction({ fileIndex: 1, fileCount: 4, localFraction: 0.5 }), 0.375);
  });

  it("refuses pre-seek zero writes that would wipe a bookmark", () => {
    assert.equal(
      shouldWriteListenProgress({ ready: false, seconds: 0, resumeSeconds: 40 }),
      false,
    );
    assert.equal(
      shouldWriteListenProgress({ ready: true, seconds: 0.2, resumeSeconds: 40 }),
      false,
    );
    assert.equal(
      shouldWriteListenProgress({ ready: true, seconds: 41, resumeSeconds: 40 }),
      true,
    );
    assert.equal(
      shouldWriteListenProgress({ ready: true, seconds: 0, resumeSeconds: 0 }),
      true,
    );
  });

  it("cycles rates through 2.5× and sleep timer options", () => {
    assert.equal(nextListenRate(2), 2.5);
    assert.equal(nextListenRate(2.5), 0.75);
    assert.equal(nextSleepTimerId("off"), "15");
    assert.equal(nextSleepTimerId("45"), "chapter");
    assert.equal(sleepTimerLabel("chapter"), "Sleep end of chapter");
  });

  it("reports chapter remaining and persist cadence", () => {
    const chapters = [
      { index: 0, title: "One", start: 0 },
      { index: 1, title: "Two", start: 100 },
    ];
    assert.equal(chapterRemainingSeconds(chapters, 40, 200), 60);
    assert.equal(chapterRemainingSeconds(chapters, 150, 200), 50);
    assert.equal(shouldPersistListenCadence({ force: true, lastPersistMs: Date.now() }), true);
    assert.equal(
      shouldPersistListenCadence({ force: false, lastPersistMs: Date.now(), nowMs: Date.now() + 50 }),
      false,
    );
    assert.equal(
      shouldPersistListenCadence({ force: false, lastPersistMs: 0, nowMs: 2000, minIntervalMs: 900 }),
      true,
    );
  });

  it("splits Hall continue rails by kind", () => {
    const { reading, listening } = splitContinueRails([
      { id: "1", kind: "book", title: "Kindred" },
      { id: "2", kind: "audiobook", title: "Dune" },
      { id: "3", kind: "comic", title: "Saga" },
    ]);
    assert.deepEqual(
      reading.map((row) => row.title),
      ["Kindred", "Saga"],
    );
    assert.deepEqual(
      listening.map((row) => row.title),
      ["Dune"],
    );
  });

  it("finds chapter neighbors for Media Session skip", () => {
    const chapters = [
      { index: 0, title: "One", start: 0 },
      { index: 1, title: "Two", start: 100 },
      { index: 2, title: "Three", start: 200 },
    ];
    assert.equal(chapterAt(chapters, 120)?.title, "Two");
    assert.equal(nextChapter(chapters, 120)?.title, "Three");
    // Mid-chapter: prev restarts current; early in chapter: prev goes back.
    assert.equal(prevChapter(chapters, 120)?.title, "Two");
    assert.equal(prevChapter(chapters, 100.2)?.title, "One");
    assert.equal(formatListenClock(3723), "1:02:03");
  });
});
