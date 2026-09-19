import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { audiobookFindHref, companionAudiobookView } from "./audiobookCompanion.js";

describe("audiobook companion CTAs", () => {
  it("hides when not applicable", () => {
    assert.equal(companionAudiobookView(null).show, false);
    assert.equal(companionAudiobookView({ applicable: false }).show, false);
  });

  it("links Listen when an audiobook is already shelved", () => {
    const view = companionAudiobookView({
      applicable: true,
      shelved: { id: "a1", title: "Dune" },
      find: { kind: "audiobook", title: "Dune", author: "Frank Herbert" },
    });
    assert.equal(view.show, true);
    assert.equal(view.listenHref, "/works/a1?listen=1");
    assert.equal(view.secondaryLabel, "Audiobook on the shelves");
    assert.match(view.findHref, /kind=audiobook/);
  });

  it("offers Find audiobook when nothing is shelved", () => {
    const view = companionAudiobookView({
      applicable: true,
      shelved: null,
      find: { kind: "audiobook", title: "Dune", author: "Frank Herbert", isbn: "9780441172719" },
    });
    assert.equal(view.primaryLabel, "Find audiobook");
    assert.match(view.findHref, /kind=audiobook/);
    assert.match(view.findHref, /title=Dune/);
    assert.equal(
      audiobookFindHref({ kind: "audiobook", title: "Dune", author: "Frank Herbert", isbn: "9780441172719" }),
      "/find?kind=audiobook&author=Frank+Herbert&title=Dune&isbn=9780441172719",
    );
  });
});
