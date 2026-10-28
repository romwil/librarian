import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "vitest";
import { fileURLToPath } from "node:url";
import { placeActionMenu, primaryActionOrder, primaryWorkAction, splitWorkActions } from "./workActionMenu.js";
import { readStyles } from "../test/styles.js";

const root = dirname(fileURLToPath(import.meta.url));

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

function withView(size, run) {
  const prior = globalThis.window;
  globalThis.window = { innerWidth: size.width, innerHeight: size.height };
  try {
    return run();
  } finally {
    if (prior === undefined) delete globalThis.window;
    else globalThis.window = prior;
  }
}

function peekAnchor(box) {
  const column = { getBoundingClientRect: () => box };
  return {
    closest(selector) {
      if (selector === ".peek" || selector === ".peek-copy") return column;
      return null;
    },
  };
}

describe("placeActionMenu", () => {
  const grip = { top: 476, bottom: 520, left: 24, width: 44, height: 44 };
  const menu = { width: 200, height: 160 };

  it("lines a peek menu up with the sheet column and opens under the grip", () => {
    const style = withView({ width: 390, height: 844 }, () =>
      placeActionMenu(grip, menu, peekAnchor({ left: 24, width: 342, top: 0, bottom: 700 })),
    );
    assert.equal(style.left, "24px");
    assert.equal(style.width, "342px");
    assert.equal(style.maxWidth, "342px");
    assert.equal(style.minWidth, "0px");
    // 520 + 8 — beneath the grip, not over Read above it.
    assert.equal(style.top, "528px");
  });

  it("clamps a peek menu that is wider than the phone", () => {
    const style = withView({ width: 390, height: 844 }, () =>
      placeActionMenu(grip, menu, peekAnchor({ left: 0, width: 400, top: 0, bottom: 700 })),
    );
    assert.equal(style.left, "8px");
    assert.equal(style.width, "374px");
  });

  it("keeps cover and work-page menus anchored to the grip", () => {
    const style = withView({ width: 1200, height: 800 }, () =>
      placeActionMenu({ top: 100, bottom: 144, left: 40 }, { width: 200, height: 80 }, {
        closest() {
          return null;
        },
      }),
    );
    assert.equal(style.left, "40px");
    assert.equal(style.top, "12px");
    assert.equal(style.width, undefined);
  });

  it("a zero-width peek column falls back to the grip anchor", () => {
    const style = withView({ width: 1200, height: 800 }, () =>
      placeActionMenu({ top: 100, bottom: 144, left: 40 }, { width: 200, height: 80 }, {
        closest(selector) {
          if (selector === ".peek") return { getBoundingClientRect: () => ({ width: 0, left: 0 }) };
          if (selector === ".peek-copy") return { getBoundingClientRect: () => ({ width: 0, left: 10 }) };
          return null;
        },
      }),
    );
    assert.equal(style.left, "40px");
    assert.equal(style.width, undefined);
  });

  it("hostile rects and a missing window stay finite", () => {
    const style = withView({ width: 1200, height: 800 }, () =>
      placeActionMenu({ top: "no", bottom: null, left: undefined }, { width: "x", height: null }, null),
    );
    assert.match(style.top, /^\d+(\.\d+)?px$/);
    assert.match(style.left, /^\d+(\.\d+)?px$/);
    const prior = globalThis.window;
    delete globalThis.window;
    try {
      assert.deepEqual(placeActionMenu(grip, menu, null), { top: "8px", left: "8px" });
    } finally {
      if (prior === undefined) delete globalThis.window;
      else globalThis.window = prior;
    }
  });
});

describe("peek grip placement in the sheet", () => {
  const peekSrc = readFileSync(join(root, "../components/WorkPeek.jsx"), "utf8");
  const menuSrc = readFileSync(join(root, "../components/WorkActionMenu.jsx"), "utf8");
  const stylesSrc = readStyles();

  it("puts the peek grip in the action row, under Read on a phone", () => {
    assert.match(peekSrc, /className="peek-action-menu"/);
    assert.match(menuSrc, /event\.stopPropagation\(\)/);
    assert.match(stylesSrc, /\.peek \.peek-action-menu\s*\{[^}]*position:\s*static/);
    const phone = stylesSrc.slice(stylesSrc.indexOf("@media (max-width: 640px)"));
    assert.match(phone, /\.peek \.peek-action-menu\s*\{[^}]*flex:\s*1 0 100%/);
    assert.match(phone, /\.peek \.peek-action-menu \.work-action-grip\s*\{[^}]*flex:\s*0 0 var\(--tap-min\)/);
  });
});
