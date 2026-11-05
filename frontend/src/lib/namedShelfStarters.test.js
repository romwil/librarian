import assert from "node:assert/strict";
import { describe, it } from "vitest";
import { NAMED_SHELF_STARTERS, shelfStarterNames } from "./namedShelfStarters.js";

describe("named shelf starters", () => {
  it("exposes three starters", () => {
    assert.equal(NAMED_SHELF_STARTERS.length, 3);
  });

  it("hides names already taken", () => {
    assert.deepEqual(shelfStarterNames([{ name: "Next up" }]), ["For the beach", "Read together"]);
  });
});
