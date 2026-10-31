import assert from "node:assert/strict";
import { describe, it } from "vitest";
import { hallChipRow } from "./hallChips.js";

describe("Hall chip row", () => {
  it("orders kinds by count then named shelves with a count", () => {
    const chips = hallChipRow({
      kind_counts: { book: 2, audiobook: 5, comic: 0, magazine: 1 },
      named_shelves: [
        { id: "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa", name: "Bedside", work_count: 3 },
        { id: "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb", name: "Empty", work_count: 0 },
      ],
    });
    assert.deepEqual(
      chips.map((chip) => chip.label),
      ["Audiobooks", "Books", "Magazines", "Bedside"],
    );
    assert.equal(chips[0].href, "/browse?kind=audiobook");
    assert.match(chips[3].href, /shelf=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa/);
  });

  it("hides empty kinds", () => {
    assert.deepEqual(hallChipRow({ kind_counts: {}, named_shelves: [] }), []);
  });
});
