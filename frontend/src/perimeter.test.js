import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "vitest";
import { readStyles } from "./test/styles.js";

const root = dirname(fileURLToPath(import.meta.url));
const repo = join(root, "..");

test("index.html has no Google Fonts and no inline script", () => {
  const html = readFileSync(join(repo, "index.html"), "utf8");
  assert.doesNotMatch(html, /fonts\.googleapis\.com/);
  assert.doesNotMatch(html, /fonts\.gstatic\.com/);
  assert.doesNotMatch(html, /<script>(?!\s*<\/script>)/);
  assert.match(html, /theme-boot\.js/);
  assert.match(html, /literata-latin-opsz-normal\.woff2/);
  assert.match(html, /source-sans-3-latin-wght-normal\.woff2/);
});

test("SPA fetch sends the household origin header", () => {
  const api = readFileSync(join(root, "api.js"), "utf8");
  assert.match(api, /"X-Librarian": "1"/);
  assert.match(api, /headers: \{ "X-Librarian": "1" \}/);
});

test("self-hosted font faces stay on Literata and Source Sans 3", () => {
  const styles = readStyles();
  assert.match(styles, /@font-face/);
  assert.match(styles, /font-family: "Literata"/);
  assert.match(styles, /font-family: "Source Sans 3"/);
  assert.match(styles, /ibm-plex-mono-latin-400-normal\.woff2/);
  assert.doesNotMatch(styles, /url\([^)]*fonts\.google/);
});
