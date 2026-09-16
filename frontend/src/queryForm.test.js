import assert from "node:assert/strict";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, it } from "node:test";
import * as esbuild from "esbuild";
import { findKindOptions, KINDS } from "./find.js";

const frontendRoot = fileURLToPath(new URL("..", import.meta.url));

async function loadQueryForm() {
  const cache = join(frontendRoot, "node_modules/.cache");
  mkdirSync(cache, { recursive: true });
  const outfile = join(cache, "librarian-queryform-test.mjs");
  await esbuild.build({
    absWorkingDir: frontendRoot,
    entryPoints: ["src/components/QueryForm.jsx"],
    bundle: true,
    format: "esm",
    outfile,
    jsx: "automatic",
    platform: "node",
    packages: "external",
  });
  return (await import(pathToFileURL(outfile).href)).default;
}

function optionValues(html) {
  return [...html.matchAll(/<option(?:\s[^>]*)?\svalue="([^"]*)"/g)].map((match) => match[1]);
}

const noop = () => {};

function renderForm(QueryForm, props) {
  return renderToStaticMarkup(
    createElement(QueryForm, {
      draft: "",
      onDraft: noop,
      kind: "",
      onKindCommit: noop,
      advanced: {},
      onAdvanced: noop,
      onSubmit: noop,
      ...props,
    }),
  );
}

describe("QueryForm kinds", () => {
  it("puts a custom kinds list in the search select", async () => {
    const QueryForm = await loadQueryForm();
    const kinds = findKindOptions(true);
    const html = renderForm(QueryForm, { variant: "search", kinds });
    assert.deepEqual(
      optionValues(html),
      kinds.map(([value]) => value),
    );
    assert.ok(html.includes('value="movie"'));
    assert.ok(html.includes(">Movie<"));
    assert.ok(html.includes('value="tv"'));
    assert.ok(html.includes('value="xxx"'));
  });

  it("keeps default Librarian kinds in the search select", async () => {
    const QueryForm = await loadQueryForm();
    const html = renderForm(QueryForm, { variant: "search" });
    assert.deepEqual(
      optionValues(html),
      KINDS.map(([value]) => value),
    );
    assert.equal(html.includes('value="movie"'), false);
  });
});
