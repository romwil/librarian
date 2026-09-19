import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  busyAction,
  busyLabel,
  doneLabel,
  enrichIsRunning,
  enrichProgressSummary,
  isBusy,
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
        result: { scanned: 3, updated: 2 },
      }),
      "Enriched 2 of 3 thin volumes",
    );
    assert.equal(enrichProgressSummary({ status: "failed", error: "No network" }), "No network");
  });
});
