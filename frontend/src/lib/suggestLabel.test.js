import assert from "node:assert/strict";
import { describe, it } from "vitest";
import { suggestDisplayLabel } from "./suggestLabel.js";

describe("suggestDisplayLabel (UX-010)", () => {
  it("strips dump paths and extensions", () => {
    assert.equal(suggestDisplayLabel("/data/dump/Born In Fire.epub"), "Born In Fire");
    assert.equal(suggestDisplayLabel("Saga #11.cbz"), "Saga #11");
  });

  it("prefers the clean title after a parenthetical dump prefix", () => {
    assert.equal(suggestDisplayLabel("(Born 1) - Born In Fire"), "Born In Fire");
  });

  it("leaves ordinary titles alone", () => {
    assert.equal(suggestDisplayLabel("The Left Hand of Darkness"), "The Left Hand of Darkness");
  });
});
