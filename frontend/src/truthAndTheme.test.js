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

function hexToRgb(hex) {
  const h = hex.replace("#", "");
  return {
    r: parseInt(h.slice(0, 2), 16),
    g: parseInt(h.slice(2, 4), 16),
    b: parseInt(h.slice(4, 6), 16),
  };
}

function relativeLuminance({ r, g, b }) {
  const channel = (value) => {
    const v = value / 255;
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

function contrastRatio(foreground, background) {
  const lighter = Math.max(relativeLuminance(hexToRgb(foreground)), relativeLuminance(hexToRgb(background)));
  const darker = Math.min(relativeLuminance(hexToRgb(foreground)), relativeLuminance(hexToRgb(background)));
  return (lighter + 0.05) / (darker + 0.05);
}

test("Lights Up body and muted tokens meet 4.5:1 on paper", () => {
  assert.ok(contrastRatio("#1c1612", "#f3ecdf") >= 4.5, "ink on paper");
  assert.ok(contrastRatio("#3a322c", "#f3ecdf") >= 4.5, "muted on paper");
  assert.ok(contrastRatio("#f4ead6", "#2a2118") >= 4.5, "cream on raised night");
});

test("peek is a solid themed panel and the overflow grip uses ink", () => {
  assert.match(stylesSrc, /\.peek\s*\{[^}]*background:\s*var\(--surface-raised\)/);
  assert.match(stylesSrc, /\.peek\.has-wash\s*\{[^}]*background:\s*var\(--surface-raised\)/);
  assert.doesNotMatch(stylesSrc, /\.peek\.has-wash\s*\{[^}]*88%/);
  assert.match(stylesSrc, /\.peek h1\s*\{[^}]*color:\s*var\(--text\)/);
  assert.match(stylesSrc, /\.work-action-grip\s*\{[^}]*color:\s*var\(--text\)/);
  assert.match(stylesSrc, /\.work-action-grip\s*\{[^}]*background:\s*var\(--surface-raised\)/);
  assert.match(stylesSrc, /\.work-sub\s*\{[^}]*color:\s*var\(--text\)/);
  assert.match(stylesSrc, /\.synopsis p\s*\{[^}]*color:\s*var\(--text\)/);
  assert.match(stylesSrc, /\.search-status\s*\{[^}]*color:\s*var\(--muted\)/);
  assert.match(stylesSrc, /\.glass h1\s*\{[^}]*color:\s*var\(--text\)/);
});

test("foyer stays a dark room", () => {
  const foyer = readFileSync(join(root, "components/GlassDoor.jsx"), "utf8");
  assert.match(foyer, /data-theme="lights-down"/);
  assert.match(stylesSrc, /\.foyer\s*\{[^}]*color:\s*var\(--text\)/);
});

test("field inputs use token ink and keep autofill fill readable", () => {
  assert.match(stylesSrc, /\.field input,\s*\.field select\s*\{[^}]*color:\s*var\(--text\)/);
  assert.match(stylesSrc, /\.field input:-webkit-autofill[\s\S]*?-webkit-text-fill-color:\s*var\(--text\)/);
  assert.match(stylesSrc, /\.field input::placeholder[\s\S]*?color:\s*color-mix\(in srgb, var\(--muted\)/);
});

test("field help ? stays out of sequential tab order", () => {
  const help = readFileSync(join(root, "components/FieldHelp.jsx"), "utf8");
  assert.match(help, /className="help-q"[\s\S]*?tabIndex=\{-1\}/);
});

test("peek chrome is not a second banner landmark", () => {
  const peek = readFileSync(join(root, "components/WorkPeek.jsx"), "utf8");
  assert.match(peek, /<div className="peek-head">/);
  assert.doesNotMatch(peek, /<header className="peek-head">/);
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
