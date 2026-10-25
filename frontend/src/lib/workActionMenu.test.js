import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { primaryActionOrder, primaryWorkAction, splitWorkActions } from "./workActionMenu.js";

describe("primaryWorkAction", () => {
  it("prefers Listen over everything else", () => {
    assert.deepEqual(
      primaryWorkAction({ canListen: true, canRead: true, canInlineOpen: true, canAsk: true }),
      { key: "listen", label: "Listen" },
    );
  });

  it("labels Continue listening only when resuming", () => {
    assert.equal(
      primaryWorkAction({ canListen: true, listenResume: true }).label,
      "Continue listening",
    );
    assert.equal(primaryWorkAction({ canListen: true, listenResume: false }).label, "Listen");
  });

  it("a caller-supplied listenLabel wins over the resume default", () => {
    assert.equal(
      primaryWorkAction({ canListen: true, listenResume: true, listenLabel: "Resume chapter 4" }).label,
      "Resume chapter 4",
    );
  });

  it("falls to Read in-app when Listen is unavailable", () => {
    assert.deepEqual(
      primaryWorkAction({ canRead: true, canInlineOpen: true, readLabel: "Read" }),
      { key: "read", label: "Read" },
    );
  });

  it("falls to inline open when neither Listen nor in-app Read applies", () => {
    assert.deepEqual(primaryWorkAction({ canInlineOpen: true, readLabel: "Open" }), {
      key: "open",
      label: "Open",
    });
  });

  it("Ask the house only wins when Listen/Read/inline-open are all false", () => {
    assert.deepEqual(primaryWorkAction({ canAsk: true, askLabel: "Ask the house" }), {
      key: "ask",
      label: "Ask the house",
    });
    // Even one candidate above it present means Ask never becomes primary.
    assert.equal(primaryWorkAction({ canRead: true, canAsk: true }).key, "read");
  });

  it("returns null when nothing qualifies (a rail card's implicit primary is the cover click)", () => {
    assert.equal(primaryWorkAction({}), null);
    assert.equal(primaryWorkAction(), null);
  });

  it("ignores hostile/garbage flags instead of throwing", () => {
    assert.equal(
      primaryWorkAction({ canListen: "yes", canRead: 1, canAsk: [] })?.key,
      "listen",
    );
  });

  it("exposes the priority order for descriptor-list builders", () => {
    assert.deepEqual(primaryActionOrder(), ["listen", "read", "open", "ask"]);
    // Returns a fresh copy each call — callers can't mutate the shared order.
    const order = primaryActionOrder();
    order.push("rogue");
    assert.deepEqual(primaryActionOrder(), ["listen", "read", "open", "ask"]);
  });
});

describe("splitWorkActions", () => {
  const actions = [
    { key: "favorite", label: "Favorite" },
    { key: "download", label: "Download" },
    { key: "promote", label: "Promote" },
  ];

  it("pulls the matching key out as primary and leaves the rest as items, order preserved", () => {
    const { primary, items } = splitWorkActions(actions, "download");
    assert.deepEqual(primary, { key: "download", label: "Download" });
    assert.deepEqual(items, [
      { key: "favorite", label: "Favorite" },
      { key: "promote", label: "Promote" },
    ]);
  });

  it("removes only the first match when keys collide", () => {
    const dup = [{ key: "x", label: "First" }, { key: "x", label: "Second" }];
    const { primary, items } = splitWorkActions(dup, "x");
    assert.deepEqual(primary, { key: "x", label: "First" });
    assert.deepEqual(items, [{ key: "x", label: "Second" }]);
  });

  it("no primary key: everything stays in the menu (the rail-card case)", () => {
    assert.deepEqual(splitWorkActions(actions, ""), { primary: null, items: actions });
    assert.deepEqual(splitWorkActions(actions), { primary: null, items: actions });
  });

  it("primary key with no match: degrades to no primary, items untouched", () => {
    assert.deepEqual(splitWorkActions(actions, "nope"), { primary: null, items: actions });
  });

  it("hostile/empty action lists never throw", () => {
    assert.deepEqual(splitWorkActions(null, "download"), { primary: null, items: [] });
    assert.deepEqual(splitWorkActions(undefined, "download"), { primary: null, items: [] });
    assert.deepEqual(splitWorkActions("not-an-array", "download"), { primary: null, items: [] });
    assert.deepEqual(splitWorkActions([null, undefined, { key: "x" }], "x"), {
      primary: { key: "x" },
      items: [],
    });
  });
});
