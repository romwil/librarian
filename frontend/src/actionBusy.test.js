import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  busyAction,
  busyLabel,
  doneLabel,
  enrichIsRunning,
  enrichPhaseLabel,
  enrichProgressSummary,
  isBusy,
  scanIsRunning,
  scanPhaseLabel,
  scanProgressSummary,
  ticketStatusNote,
} from "./actionBusy.js";

describe("actionBusy", () => {
  it("maps review actions to busy and done copy", () => {
    assert.equal(busyLabel("apply"), "Applying…");
    assert.equal(busyLabel("suggest"), "Suggesting…");
    assert.equal(doneLabel("skip"), "Skipped.");
    assert.equal(busyLabel("unknown"), "Working…");
  });

  it("reads per-ticket busy keys", () => {
    const busy = { a: "apply", b: true };
    assert.equal(isBusy(busy, "a"), true);
    assert.equal(busyAction(busy, "a"), "apply");
    assert.equal(busyAction(busy, "b"), "working");
    assert.equal(ticketStatusNote(busy, {}, "a"), "Applying…");
    assert.equal(ticketStatusNote({}, { a: "Applied." }, "a"), "Applied.");
  });

  it("summarizes enrich progress for the Settings panel", () => {
    assert.equal(enrichIsRunning({ status: "running" }), true);
    assert.equal(enrichPhaseLabel("enriching"), "enriching");
    assert.equal(
      enrichProgressSummary({
        status: "running",
        done: 2,
        total: 5,
        current_title: "Dune",
      }),
      "2 of 5 · Dune",
    );
    assert.equal(
      enrichProgressSummary({
        status: "completed",
        result: { scanned: 3, updated: 2, skipped: 1, errors: 1 },
      }),
      "Enriched 2 of 3 thin volumes · 1 skipped · 1 failed",
    );
    assert.equal(enrichProgressSummary({ status: "failed", error: "No network" }), "No network");
  });

  it("summarizes scan progress for the Settings panel", () => {
    assert.equal(scanIsRunning({ status: "running" }), true);
    assert.equal(scanPhaseLabel("listing"), "listing");
    assert.equal(
      scanProgressSummary({
        status: "running",
        done: 1,
        total: 4,
        current_title: "Left Hand",
      }),
      "1 of 4 · Left Hand",
    );
    assert.equal(
      scanProgressSummary({
        status: "completed",
        result: { scanned: 4, created: 2, updated: 2, review: 1, errors: 0 },
      }),
      "Scanned 4 · 2 new · 2 updated · 1 need review",
    );
    assert.equal(scanProgressSummary({ status: "failed", error: "Disk gone" }), "Disk gone");
  });
});
