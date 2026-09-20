import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  filterBrowseEntries,
  ingestIsRunning,
  ingestPhaseLabel,
  ingestProgressSummary,
  ingestResultMessage,
  ingestSourcePath,
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
      "Organizing · 2 of 5 · shelved 1 · needs you 1 · Christine",
    );
    assert.equal(
      ingestProgressSummary({
        status: "completed",
        result: { shelved: 3, review: 2, skipped: 1 },
      }),
      "Finished — shelved 3, needs you 2, skipped 1",
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
  });
});
