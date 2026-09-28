import assert from "node:assert/strict";
import test from "node:test";
import { renormalizeIsAvailable, renormalizePresence, renormalizeReadyCount } from "./lib/calibreRenormalize.js";
import { gapsGiftTitle, gapsGiftPresence } from "./lib/gapsAsGifts.js";
import { didYouMeanList, didYouMeanPresence, searchForgave } from "./lib/searchForgive.js";

test("calibre renormalize helpers", () => {
  assert.equal(renormalizeIsAvailable(null), false);
  assert.equal(renormalizeReadyCount({ counts: { copy: 3 } }), 3);
  assert.match(renormalizePresence(null), /No Calibre|waiting/i);
});

test("gaps as gifts copy", () => {
  assert.equal(gapsGiftTitle(), "Gaps as gifts");
  assert.match(gapsGiftPresence({ gaps: [] }), /whole/i);
});

test("search forgive helpers", () => {
  assert.deepEqual(didYouMeanList({ did_you_mean: ["Dune", ""] }), ["Dune"]);
  assert.equal(searchForgave({ forgave: true }), true);
  assert.match(didYouMeanPresence(["Dune"]), /Did you mean/);
});
