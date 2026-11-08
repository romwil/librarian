import assert from "node:assert/strict";
import { describe, it } from "vitest";
import {
  DESK_BADGE_SHOW_COUNT_AT,
  deskBadgeMode,
  deskMenuSortingLabel,
  deskNavAriaLabel,
  deskNavVisibleLabel,
} from "./deskBadge.js";

describe("deskBadge (PRD-005)", () => {
  it("escalates only above the documented threshold", () => {
    assert.equal(DESK_BADGE_SHOW_COUNT_AT, 5);
    assert.equal(deskBadgeMode(0), "clear");
    assert.equal(deskBadgeMode(1), "quiet");
    assert.equal(deskBadgeMode(5), "quiet");
    assert.equal(deskBadgeMode(6), "loud");
    assert.equal(deskBadgeMode(27), "loud");
    assert.equal(deskBadgeMode("3"), "quiet");
    assert.equal(deskBadgeMode(null), "clear");
    assert.equal(deskBadgeMode(-2), "clear");
  });

  it("keeps chrome labels calm until loud", () => {
    assert.equal(deskNavVisibleLabel("Sorting", 0), "Sorting");
    assert.equal(deskNavVisibleLabel("Sorting", 3), "Sorting");
    assert.equal(deskNavVisibleLabel("Sorting", 5), "Sorting");
    assert.equal(deskNavVisibleLabel("Sorting", 6), "Sorting 6");
    assert.equal(deskNavVisibleLabel("Desk", 27), "Desk 27");
  });

  it("speaks the exact count in aria and the card menu", () => {
    assert.equal(deskNavAriaLabel("Sorting", 0), "Sorting");
    assert.match(deskNavAriaLabel("Sorting", 3), /3 open/);
    assert.match(deskNavAriaLabel("Desk", 27), /27 open/);
    assert.equal(deskMenuSortingLabel(0), "Sorting");
    assert.equal(deskMenuSortingLabel(3), "Sorting (3)");
    assert.equal(deskMenuSortingLabel(27), "Sorting (27)");
  });
});
