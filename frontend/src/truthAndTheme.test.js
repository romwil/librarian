import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "vitest";
import { readStyles } from "./test/styles.js";

const root = dirname(fileURLToPath(import.meta.url));
const stylesSrc = readStyles();

test("Lights Up keeps ink text and gilt-as-text tokens", () => {
  assert.match(stylesSrc, /\[data-theme="lights-up"\][\s\S]*--text:\s*#1c1612/);
  assert.match(stylesSrc, /\[data-theme="lights-up"\][\s\S]*--gilt-text:\s*#6e6256/);
  assert.match(stylesSrc, /\[data-theme="lights-up"\][\s\S]*--control-border:\s*#857563/);
  assert.match(stylesSrc, /\[data-theme="lights-down"\][\s\S]*--gilt:\s*#e4c078/);
});

test("foyer stays a dark room", () => {
  const foyer = readFileSync(join(root, "components/GlassDoor.jsx"), "utf8");
  assert.match(foyer, /data-theme="lights-down"/);
});

test("cover grip sits below the art, not over Read", () => {
  const cover = readFileSync(join(root, "components/CoverCard.jsx"), "utf8");
  const frameClose = cover.indexOf("</div>", cover.indexOf("cover-frame"));
  const grip = cover.indexOf("<WorkActionMenu");
  assert.ok(frameClose > 0 && grip > frameClose);
  assert.match(stylesSrc, /\.work-action-menu\s*\{[^}]*position:\s*static/);
});

test("Settings RSS and notification prefs are not nested forms", () => {
  const rss = readFileSync(join(root, "components/RssPanel.jsx"), "utf8");
  const notes = readFileSync(join(root, "components/NotificationsPrefsPanel.jsx"), "utf8");
  assert.doesNotMatch(rss, /<form/);
  assert.doesNotMatch(notes, /<form/);
  assert.match(rss, /Subscribe/);
  assert.match(notes, /Save preferences/);
});

test("opening a work page does not mint Continue progress", () => {
  const work = readFileSync(join(root, "pages/WorkPage.jsx"), "utf8");
  assert.doesNotMatch(work, /api\.progress\(payload\.work\.id\)/);
  assert.match(work, /share:\s*Boolean\(share\)/);
});
