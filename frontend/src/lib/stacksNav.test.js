import assert from "node:assert/strict";
import { describe, it } from "vitest";
import { stacksNavState } from "./stacksNav.js";

describe("stacksNavState", () => {
  it("highlights Stacks on bare /browse", () => {
    assert.deepEqual(stacksNavState("/browse", ""), { stacks: true, favorites: false });
  });

  it("highlights Stacks on any non-favorites /browse query", () => {
    assert.deepEqual(stacksNavState("/browse", "?kind=book&sort=title"), {
      stacks: true,
      favorites: false,
    });
  });

  it("highlights Favorites only on shelf=favorites", () => {
    assert.deepEqual(stacksNavState("/browse", "?shelf=favorites"), {
      stacks: false,
      favorites: true,
    });
    // Case-insensitive, and tolerant of other params alongside it.
    assert.deepEqual(stacksNavState("/browse", "?kind=book&shelf=Favorites"), {
      stacks: false,
      favorites: true,
    });
  });

  it("highlights neither off /browse", () => {
    assert.deepEqual(stacksNavState("/", ""), { stacks: false, favorites: false });
    assert.deepEqual(stacksNavState("/works/123", "?shelf=favorites"), {
      stacks: false,
      favorites: false,
    });
  });

  it("tolerates a missing leading '?' and hostile shelf values", () => {
    assert.deepEqual(stacksNavState("/browse", "shelf=favorites"), {
      stacks: false,
      favorites: true,
    });
    assert.deepEqual(stacksNavState("/browse", "?shelf=<script>"), {
      stacks: true,
      favorites: false,
    });
  });
});
