import assert from "node:assert/strict";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, it } from "node:test";
import * as esbuild from "esbuild";

const frontendRoot = fileURLToPath(new URL("..", import.meta.url));

async function loadControl() {
  const cache = join(frontendRoot, "node_modules/.cache");
  mkdirSync(cache, { recursive: true });
  const outfile = join(cache, "librarian-search-mode-test.mjs");
  await esbuild.build({
    absWorkingDir: frontendRoot,
    entryPoints: ["src/components/SearchModeControl.jsx"],
    bundle: true,
    format: "esm",
    outfile,
    jsx: "automatic",
    platform: "node",
    packages: "external",
  });
  return import(pathToFileURL(outfile).href);
}

describe("search mode control", () => {
  it("offers title, author, ISBN, series, and narrator as one choice", async () => {
    const { default: SearchModeControl, SEARCH_MODES } = await loadControl();
    const html = renderToStaticMarkup(
      createElement(SearchModeControl, { mode: "isbn", onMode: () => {} }),
    );
    assert.equal(SEARCH_MODES.length, 5);
    assert.match(html, /role="radiogroup"/);
    assert.match(html, /aria-label="Search mode"/);
    for (const [value, label] of SEARCH_MODES) {
      assert.match(html, new RegExp(`data-testid="search-mode-${value}"`));
      assert.match(html, new RegExp(`>${label}<`));
    }
    function buttonAt(testid) {
      const at = html.indexOf(`data-testid="${testid}"`);
      const start = html.lastIndexOf("<button", at);
      return html.slice(start, html.indexOf("</button>", at));
    }
    assert.match(buttonAt("search-mode-isbn"), /aria-checked="true"/);
    assert.match(buttonAt("search-mode-title"), /aria-checked="false"/);
  });
});
