import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "vitest";

const root = dirname(fileURLToPath(import.meta.url));
const railSrc = readFileSync(join(root, "components/Rail.jsx"), "utf8");
const hallSrc = readFileSync(join(root, "pages/HallPage.jsx"), "utf8");
const motionSrc = readFileSync(join(root, "styles/motion.css"), "utf8");

test("Continue rails on Hall render only when they have items", () => {
  assert.match(hallSrc, /continueRailItems\(hall\?\.continue\)/);
  assert.match(hallSrc, /continueRailItems\(hall\?\.continue_listening\)/);
  assert.match(hallSrc, /title="Continue reading"/);
  assert.match(hallSrc, /title="Continue listening"/);
  assert.doesNotMatch(hallSrc, /empty=\{hall/);
  assert.match(railSrc, /if \(!items\?\.length\)/);
  assert.match(railSrc, /return empty \?/);
});

test("motion tokens include breath and cover-settle with reduced-motion", () => {
  assert.match(motionSrc, /--motion-breath/);
  assert.match(motionSrc, /@keyframes shelf-breath/);
  assert.match(motionSrc, /@keyframes cover-settle/);
  assert.match(motionSrc, /\.cover-settle/);
  assert.match(motionSrc, /prefers-reduced-motion:\s*reduce/);
  assert.match(motionSrc, /--motion-breath:\s*1ms/);
});

test("Hall leaves lamp-wash rituals off the collection page", () => {
  assert.doesNotMatch(hallSrc, /hall-lamp-ritual/);
  assert.doesNotMatch(hallSrc, /welcomeBackCopy/);
  assert.match(motionSrc, /data-lamp-period="dawn"/);
  assert.match(motionSrc, /data-lamp-period="dusk"/);
  assert.match(motionSrc, /peek-ritual/);
  assert.match(motionSrc, /finish-ritual/);
});
