import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { undoIsAvailable, undoLabel, undoPresence } from "./lib/groomingUndo.js";

describe("groomingUndo", () => {
  it("stays calm when nothing is recoverable", () => {
    assert.equal(undoIsAvailable(null), false);
    assert.equal(undoIsAvailable({ available: false }), false);
    assert.match(undoPresence({}), /No recent tend|calm/i);
  });

  it("surfaces an available undo with warm presence", () => {
    const undo = { available: true, label: "Purge shells", presence: "Purge shells can still be undone." };
    assert.equal(undoIsAvailable(undo), true);
    assert.equal(undoLabel(undo), "Purge shells");
    assert.match(undoPresence(undo), /still be undone/);
  });
});
