import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { describe, it } from "vitest";
import { fileURLToPath } from "node:url";
import { placeProfileMenu } from "./profileMenu.js";
import { readStyles } from "../test/styles.js";

const root = dirname(fileURLToPath(import.meta.url));

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

describe("placeProfileMenu", () => {
  // Topbar chip near the top-right, tall owner panel.
  const chip = { top: 12, bottom: 48, left: 1080, right: 1180, width: 100, height: 36 };
  const tall = { width: 240, height: 520 };

  it("opens below the chip when the panel fits", () => {
    const style = withView({ width: 1200, height: 900 }, () =>
      placeProfileMenu(chip, { width: 240, height: 280 }),
    );
    assert.equal(style.top, "56px");
    assert.equal(style.left, "940px");
    assert.equal(style.maxHeight, "836px");
  });

  it("clamps a tall owner panel into the viewport and sets maxHeight", () => {
    const style = withView({ width: 1200, height: 500 }, () => placeProfileMenu(chip, tall));
    // Prefer below (56) but 520px overflows 500 — pin to margin and scroll via maxHeight.
    assert.equal(style.top, "8px");
    assert.equal(style.maxHeight, "484px");
    assert.match(style.left, /^\d+(\.\d+)?px$/);
  });

  it("flips above when there is more room above the chip", () => {
    const lowChip = { top: 620, bottom: 656, left: 200, right: 300, width: 100, height: 36 };
    const style = withView({ width: 800, height: 700 }, () =>
      placeProfileMenu(lowChip, { width: 220, height: 200 }),
    );
    // above = 620 - 8 - 200 = 412; below would overflow (656+8+200 > 692)
    assert.equal(style.top, "412px");
    assert.equal(style.left, "80px");
  });

  it("right-aligns and keeps a phone panel on-screen at 390", () => {
    const phoneChip = { top: 10, bottom: 46, left: 330, right: 378, width: 48, height: 36 };
    const style = withView({ width: 390, height: 844 }, () =>
      placeProfileMenu(phoneChip, { width: 260, height: 600 }),
    );
    assert.equal(style.top, "54px");
    // 378 - 260 = 118; still inside 390 - 8
    assert.equal(style.left, "118px");
    assert.equal(style.maxHeight, "782px");
  });

  it("hostile rects and a missing window stay finite", () => {
    const style = withView({ width: 1200, height: 800 }, () =>
      placeProfileMenu({ top: "no", bottom: null, right: undefined }, { width: "x", height: null }),
    );
    assert.match(style.top, /^\d+(\.\d+)?px$/);
    assert.match(style.left, /^\d+(\.\d+)?px$/);
    assert.match(style.maxHeight, /^\d+(\.\d+)?px$/);
    const prior = globalThis.window;
    delete globalThis.window;
    try {
      assert.deepEqual(placeProfileMenu(chip, tall), { top: "8px", left: "8px" });
    } finally {
      if (prior === undefined) delete globalThis.window;
      else globalThis.window = prior;
    }
  });
});

describe("ProfileMenu portals with placement", () => {
  const menuSrc = readFileSync(join(root, "../components/ProfileMenu.jsx"), "utf8");
  const stylesSrc = readStyles();

  it("uses placeProfileMenu through the shared anchored popover", () => {
    assert.match(menuSrc, /placeProfileMenu/);
    assert.match(menuSrc, /createPortal/);
    assert.match(menuSrc, /anchorSelector:\s*"\.profile-menu-trigger"/);
    assert.match(menuSrc, /placement:\s*placeProfileMenu/);
    assert.match(menuSrc, /popoverStyle/);
  });

  it("gives the panel a viewport max-height and scroll safety net", () => {
    assert.match(stylesSrc, /\.profile-menu-panel\s*\{[^}]*position:\s*fixed/s);
    assert.match(stylesSrc, /\.profile-menu-panel\s*\{[^}]*overflow-y:\s*auto/s);
    assert.match(stylesSrc, /\.profile-menu-panel\s*\{[^}]*max-height:\s*calc\(100dvh/s);
    assert.match(stylesSrc, /--mobile-tabbar-clearance/);
  });
});
