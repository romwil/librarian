import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  filterBrowseEntries,
  ingestDisplayPath,
  ingestIsRunning,
  ingestLegacyJob,
  ingestLooksLikeProgress,
  ingestPhaseLabel,
  ingestProgressPercent,
  ingestProgressSummary,
  ingestProgressTallies,
  ingestResultMessage,
  ingestSourcePath,
  ingestTallyLines,
  isSkippedBrowseName,
} from "./ingest.js";
import { ADD_TO_LIBRARY_LEDE, WATCH_FOLDER_LEDE } from "./copy.js";

describe("add to library browse", () => {
  it("skips hidden and desktop junk names", () => {
    assert.equal(isSkippedBrowseName(".DS_Store"), true);
    assert.equal(isSkippedBrowseName("._Book.epub"), true);
    assert.equal(isSkippedBrowseName("Thumbs.db"), true);
    assert.equal(isSkippedBrowseName("Le Guin - Title.epub"), false);
    assert.equal(
      filterBrowseEntries([
        { name: ".DS_Store", kind: "file" },
        { name: "inbox", kind: "dir" },
        { name: "Book.epub", kind: "file" },
      ])
        .map((entry) => entry.name)
        .join(","),
      "inbox,Book.epub",
    );
  });

  it("uses Reading Room copy, not an import wizard", () => {
    assert.match(ADD_TO_LIBRARY_LEDE, /\/data/);
    assert.match(ADD_TO_LIBRARY_LEDE, /Review/);
    assert.doesNotMatch(ADD_TO_LIBRARY_LEDE, /wizard|import/i);
    assert.match(WATCH_FOLDER_LEDE, /drop folder/i);
    assert.match(WATCH_FOLDER_LEDE, /library root/i);
  });

  it("reads the source path from ingest jobs, not an nzo name", () => {
    assert.equal(ingestSourcePath({ nzo_id: "nzo_1", storage_path: "/data/complete" }), "");
    assert.equal(
      ingestSourcePath({
        payload: { source: "ingest", path: "/data/inbox/Book.epub" },
        storage_path: "/data/inbox/Book.epub",
      }),
      "/data/inbox/Book.epub",
    );
    assert.equal(
      ingestSourcePath({ payload: { source: "watch" }, storage_path: "/data/inbox/Album" }),
      "/data/inbox/Album",
    );
  });

  it("surfaces failed ingest job.error instead of Failed — title only", () => {
    assert.deepEqual(
      ingestResultMessage(
        {
          status: "failed",
          title: "books",
          error: "Nothing to identify in here — empty or only junk files.",
        },
        "/data/books",
      ),
      {
        kind: "error",
        text: "Nothing to identify in here — empty or only junk files.",
      },
    );
    assert.deepEqual(ingestResultMessage({ status: "failed", title: "books" }, "/data/books"), {
      kind: "error",
      text: "Failed — books",
    });
    assert.deepEqual(ingestResultMessage({ status: "organized", title: "Dune" }, "/data/x"), {
      kind: "status",
      text: "Arrived — Dune",
    });
  });

  it("summarizes live ingest progress with counts and phase", () => {
    assert.equal(ingestIsRunning({ status: "running" }), true);
    assert.equal(ingestIsRunning({ status: "completed" }), false);
    assert.equal(ingestPhaseLabel("organizing"), "organizing");
    assert.equal(
      ingestProgressSummary({
        status: "running",
        phase: "organizing",
        done: 2,
        total: 5,
        shelved: 1,
        review: 1,
        current_title: "Christine",
      }),
      "Organizing · 2 of 5 · 40% · added 1 · needs you 1 · Christine",
    );
    assert.equal(ingestProgressPercent({ done: 2, total: 5 }), 40);
    assert.equal(ingestProgressPercent({ done: 0, total: 0 }), null);
    assert.equal(
      ingestProgressSummary({
        status: "completed",
        result: { seen: 6, shelved: 3, review: 2, skipped: 0, duplicates: 1 },
      }),
      "Finished — seen 6, added 3, ignored duplicates 1, needs you 2",
    );
    assert.equal(ingestProgressSummary({ status: "failed", error: "Path gone" }), "Path gone");
    assert.equal(ingestProgressSummary({ status: "idle" }), "");
    assert.equal(
      ingestProgressSummary({
        status: "failed",
        error: "Shelving stopped — the lamp was restarted. Try Add again.",
      }),
      "Shelving stopped — the lamp was restarted. Try Add again.",
    );
    assert.match(
      ingestProgressSummary({
        status: "running",
        phase: "scanning",
        total: 0,
        volumes_found: 12,
        files_found: 24,
        duplicates: 2,
        current_title: "Days of Awe (8390)",
      }),
      /Scanning · found 12 volumes · 24 files · 2 duplicates · Days of Awe/,
    );
  });

  it("shortens deep paths and builds tally lines", () => {
    assert.equal(
      ingestDisplayPath("/data/media/newlib/Abby Jimenez/Just for the Summer (10103)"),
      "…/media/newlib/Abby Jimenez/Just for the Summer (10103)",
    );
    assert.deepEqual(
      ingestProgressTallies({
        status: "completed",
        result: { seen: 10, shelved: 7, duplicates: 2, review: 1 },
      }),
      {
        seen: 10,
        shelved: 7,
        review: 1,
        skipped: 0,
        duplicates: 2,
        errors: 0,
        volumes: 0,
        files: 0,
      },
    );
    const lines = ingestTallyLines({
      status: "completed",
      result: { seen: 10, shelved: 7, duplicates: 2, review: 1 },
    });
    assert.ok(lines.includes("Seen 10"));
    assert.ok(lines.includes("Added 7"));
    assert.ok(lines.includes("Ignored duplicates 2"));
    assert.ok(lines.includes("Needs you 1"));
  });

  it("does not treat progress blobs or empty job objects as legacy jobs", () => {
    assert.equal(
      ingestLegacyJob({
        status: "running",
        phase: "organizing",
        done: 1,
        total: 10,
        kicked_off: true,
        job: {},
      }),
      null,
    );
    assert.equal(ingestLooksLikeProgress({ status: "running", phase: "scanning", done: 0, total: 3 }), true);
    assert.equal(ingestLegacyJob({ job: {} }), null);
    assert.deepEqual(ingestLegacyJob({ job: { status: "identifying", title: "Dune" } }), {
      status: "identifying",
      title: "Dune",
    });
    assert.deepEqual(ingestResultMessage({}, "/data/media/newlib"), {
      kind: "status",
      text: "On the way — /data/media/newlib",
    });
  });
});
