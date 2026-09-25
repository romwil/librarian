import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const root = dirname(fileURLToPath(import.meta.url));
const tonightSrc = readFileSync(join(root, "components/TonightShelf.jsx"), "utf8");
const railSrc = readFileSync(join(root, "components/Rail.jsx"), "utf8");
const hallSrc = readFileSync(join(root, "pages/HallPage.jsx"), "utf8");
const motionSrc = readFileSync(join(root, "styles/motion.css"), "utf8");
const stylesSrc = readFileSync(join(root, "styles.css"), "utf8");

test("Tonight’s Shelf keeps lamp presence copy and alive chrome", () => {
  assert.match(tonightSrc, /Pick up where you left the lamp/);
  assert.match(tonightSrc, /The room kept your place/);
  assert.match(tonightSrc, /tonight-shelf-alive/);
  assert.match(tonightSrc, /tonight-lamp-glow/);
  assert.match(tonightSrc, /cover-settle/);
  assert.match(tonightSrc, /aria-label="Tonight’s shelf"/);
});

test("Continue rails on Hall use lamp presence kickers", () => {
  assert.match(hallSrc, /Where you left the lamp/);
  assert.match(hallSrc, /Volumes waiting under the lamp/);
  assert.match(hallSrc, /presence/);
  assert.match(railSrc, /presence = false/);
  assert.match(railSrc, /is-continue-presence/);
  assert.match(railSrc, /cover-settle/);
});

test("motion tokens include breath and cover-settle with reduced-motion", () => {
  assert.match(motionSrc, /--motion-breath/);
  assert.match(motionSrc, /@keyframes shelf-breath/);
  assert.match(motionSrc, /@keyframes cover-settle/);
  assert.match(motionSrc, /\.tonight-lamp-glow/);
  assert.match(motionSrc, /\.cover-settle/);
  assert.match(motionSrc, /prefers-reduced-motion:\s*reduce/);
  assert.match(motionSrc, /--motion-breath:\s*1ms/);
});

test("Tonight’s Shelf surface uses lamp atmosphere in styles", () => {
  assert.match(stylesSrc, /\.tonight-shelf\s*\{/);
  assert.match(stylesSrc, /\.tonight-presence/);
  assert.match(stylesSrc, /var\(--lamp\)/);
});
