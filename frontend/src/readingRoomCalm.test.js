import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import {
  READER_CHROME_IDLE_MS,
  prefersReducedMotion,
  readerCalmClassNames,
} from "./lib/readingRoomCalm.js";
import { EPUB_READER_STYLES } from "./reader.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

describe("reading room calm", () => {
  it("builds calm class names and skips dim under reduced motion", () => {
    assert.equal(readerCalmClassNames(), "reader reader-calm");
    assert.equal(readerCalmClassNames({ chromeDim: true }), "reader reader-calm is-chrome-dim");
    assert.equal(
      readerCalmClassNames({ chromeDim: true, reducedMotion: true }),
      "reader reader-calm",
    );
    assert.ok(READER_CHROME_IDLE_MS > 1000);
  });

  it("detects prefers-reduced-motion from a media stub", () => {
    assert.equal(
      prefersReducedMotion(() => ({ matches: true })),
      true,
    );
    assert.equal(
      prefersReducedMotion(() => ({ matches: false })),
      false,
    );
  });

  it("EPUB styles soften line height for long sessions", () => {
    assert.match(EPUB_READER_STYLES, /line-height:\s*1\.65/);
    assert.match(EPUB_READER_STYLES, /max-width:\s*38rem/);
  });

  it("Reader ships calm chrome with idle dim", () => {
    const src = readFileSync(join(root, "src/components/Reader.jsx"), "utf8");
    assert.match(src, /readerCalmClassNames/);
    assert.match(src, /READER_CHROME_IDLE_MS/);
    assert.match(src, /data-calm="true"/);
    assert.match(src, /chromeDim/);
  });

  it("styles tune margins and lights-up/down for calm reading", () => {
    const styles = readFileSync(join(root, "src/styles.css"), "utf8");
    assert.match(styles, /\.reader\.reader-calm/);
    assert.match(styles, /html\[data-theme="lights-down"\] \.reader\.reader-calm/);
    assert.match(styles, /html\[data-theme="lights-up"\] \.reader\.reader-calm/);
    assert.match(styles, /padding-inline:\s*max\(var\(--gutter\),\s*calc\(\(100% - 42rem\) \/ 2\)\)/);
  });

  it("motion respects reduced-motion for calm open", () => {
    const motion = readFileSync(join(root, "src/styles/motion.css"), "utf8");
    assert.match(motion, /\.reader\.reader-calm/);
    assert.match(motion, /prefers-reduced-motion/);
  });
});
