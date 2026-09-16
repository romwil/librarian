import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { createElement, useState } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import * as esbuild from "esbuild";

const frontendRoot = fileURLToPath(new URL("..", import.meta.url));

async function loadTypeahead() {
  const cache = join(frontendRoot, "node_modules/.cache");
  mkdirSync(cache, { recursive: true });
  const outfile = join(cache, "librarian-typeahead-test.mjs");
  await esbuild.build({
    absWorkingDir: frontendRoot,
    entryPoints: ["src/components/TypeaheadField.jsx"],
    bundle: true,
    format: "esm",
    outfile,
    jsx: "automatic",
    platform: "node",
    packages: "external",
  });
  return import(pathToFileURL(outfile).href);
}

describe("TypeaheadField", () => {
  it("exports typeahead field allowlist", async () => {
    const mod = await loadTypeahead();
    assert.equal(mod.isTypeaheadField("author"), true);
    assert.equal(mod.isTypeaheadField("artist"), true);
    assert.equal(mod.isTypeaheadField("album"), true);
    assert.equal(mod.isTypeaheadField("year"), true);
    assert.equal(mod.isTypeaheadField("isbn"), false);
    assert.equal(mod.isTypeaheadField("issue"), false);
  });

  it("renders a combobox that keeps freeform value", async () => {
    const mod = await loadTypeahead();
    function Harness() {
      const [value, setValue] = useState("Frank");
      return createElement(mod.default, {
        id: "ta-author",
        field: "author",
        kind: "book",
        value,
        onChange: setValue,
        onEnterSubmit: () => {},
      });
    }
    const html = renderToStaticMarkup(createElement(Harness));
    assert.match(html, /role="combobox"/);
    assert.match(html, /value="Frank"/);
    assert.match(html, /aria-autocomplete="list"/);
  });
});
