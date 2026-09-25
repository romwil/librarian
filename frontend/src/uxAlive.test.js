import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const root = dirname(fileURLToPath(import.meta.url));
const stylesSrc = readFileSync(join(root, "styles.css"), "utf8");
const motionSrc = readFileSync(join(root, "styles/motion.css"), "utf8");
const warmLoadSrc = readFileSync(join(root, "components/WarmLoad.jsx"), "utf8");
const queueSrc = readFileSync(join(root, "pages/QueuePage.jsx"), "utf8");
const browseSrc = readFileSync(join(root, "pages/BrowsePage.jsx"), "utf8");
const workSrc = readFileSync(join(root, "pages/WorkPage.jsx"), "utf8");
const peopleSrc = readFileSync(join(root, "pages/PeoplePage.jsx"), "utf8");
const settingsSrc = readFileSync(join(root, "pages/SettingsPage.jsx"), "utf8");
const inboxSrc = readFileSync(join(root, "pages/InboxPage.jsx"), "utf8");

test("styles.css imports motion tokens", () => {
  assert.match(stylesSrc, /@import\s+"\.\/styles\/motion\.css"/);
  assert.match(stylesSrc, /--fg:\s*#f4ead6/);
  assert.match(stylesSrc, /html\[data-theme="lights-up"\][\s\S]*--fg:\s*#1a1208/);
});

test("motion.css ships settle, warm, and presence tokens with reduced-motion", () => {
  assert.match(motionSrc, /--motion-settle/);
  assert.match(motionSrc, /--motion-warm/);
  assert.match(motionSrc, /--motion-presence/);
  assert.match(motionSrc, /--motion-breath/);
  assert.match(motionSrc, /@keyframes page-settle/);
  assert.match(motionSrc, /@keyframes lamp-warm/);
  assert.match(motionSrc, /@keyframes shelf-breath/);
  assert.match(motionSrc, /@keyframes cover-settle/);
  assert.match(motionSrc, /@media \(prefers-reduced-motion:\s*reduce\)/);
  assert.match(motionSrc, /\.page-settle/);
});

test("WarmLoad is the shared warm skeleton", () => {
  assert.match(warmLoadSrc, /Warming the lamp/);
  assert.match(warmLoadSrc, /warm-load-skeleton/);
  assert.match(warmLoadSrc, /aria-busy/);
});

test("Queue / Browse / Work / People / Settings / Inbox use warm loads", () => {
  assert.match(queueSrc, /WarmLoad/);
  assert.match(queueSrc, /Warming the lamp on the Queue/);
  assert.match(browseSrc, /Warming the lamp on these stacks/);
  assert.match(workSrc, /Warming the lamp on this volume/);
  assert.match(peopleSrc, /Warming the lamp on the household roll/);
  assert.match(settingsSrc, /Warming the lamp on Settings/);
  assert.match(inboxSrc, /Warming the lamp on the desk/);
});

test("alerts and callouts use fg ink for contrast", () => {
  assert.match(stylesSrc, /\.alert\s*\{[\s\S]*?color:\s*var\(--fg/);
  assert.match(stylesSrc, /\.callout\s*\{[\s\S]*?color:\s*var\(--fg/);
});
