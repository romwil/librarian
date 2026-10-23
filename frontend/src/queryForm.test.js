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

  it("morphs Search advanced fields with the kind chip", async () => {
    const QueryForm = await loadQueryForm();
    const music = renderForm(QueryForm, { variant: "search", kind: "music" });
    assert.match(music, /data-testid="search-advanced"/);
    assert.match(music, /data-kind="music"/);
    assert.match(music, />Artist</);
    assert.match(music, />Album</);
    assert.match(music, />Year</);
    assert.match(music, /role="combobox"/);
    assert.equal(music.includes(">ISBN<"), false);
    assert.equal(music.includes(">Author<"), false);
    assert.equal(music.includes(">Series<"), false);
    assert.match(music, />More ways to search</);
    assert.equal(music.includes(">Advanced<"), false);
    assert.equal(music.includes("same page"), false);
    assert.match(music, /role="search"/);
    assert.match(music, />Search</);

    const comic = renderForm(QueryForm, { variant: "search", kind: "comic" });
    assert.match(comic, /data-kind="comic"/);
    assert.match(comic, />Series</);
    assert.match(comic, />Issue</);
    assert.equal(comic.includes(">ISBN<"), false);
    assert.equal(comic.includes(">Artist<"), false);

    const book = renderForm(QueryForm, { variant: "search", kind: "book" });
    assert.match(book, />Title</);
    assert.match(book, />Author</);
    assert.match(book, />ISBN</);
    assert.equal(book.includes(">Artist<"), false);

    const audio = renderForm(QueryForm, { variant: "search", kind: "audiobook" });
    assert.match(audio, />Title</);
    assert.match(audio, />Author</);
    assert.match(audio, />ISBN</);
    assert.equal(audio.includes(">Album<"), false);

    const all = renderForm(QueryForm, { variant: "search", kind: "" });
    assert.match(all, /data-kind="all"/);
    assert.equal(all.includes(">ISBN<"), false);
    assert.equal(all.includes(">Artist<"), false);
  });

  it("morphs Find fields the same way without the Advanced shell", async () => {
    const QueryForm = await loadQueryForm();
    const music = renderForm(QueryForm, { variant: "find", kind: "music" });
    assert.match(music, /data-testid="find-fields"/);
    assert.match(music, /data-kind="music"/);
    assert.match(music, />Artist</);
    assert.match(music, />Album</);
    assert.equal(music.includes("search-advanced"), false);
    assert.equal(music.includes(">ISBN<"), false);
  });

  it("can open More ways to search instead of leaving fields closed", async () => {
    const QueryForm = await loadQueryForm();
    const closed = renderForm(QueryForm, { variant: "search", kind: "book" });
    assert.match(closed, /data-testid="search-advanced"/);
    assert.doesNotMatch(closed, /<details class="advanced" open/);
    const opened = renderForm(QueryForm, { variant: "search", kind: "book", advancedOpen: true });
    assert.match(opened, /<details class="advanced" open/);
    assert.match(opened, />Title</);
    assert.match(opened, />Author</);
    assert.match(opened, />ISBN</);
  });

  it("hero variant is just the field", async () => {
    const QueryForm = await loadQueryForm();
    const html = renderForm(QueryForm, { variant: "hero", placeholder: "Title, author, or ISBN" });
    assert.match(html, /role="search"/);
    assert.match(html, /Title, author, or ISBN/);
    assert.match(html, />Search</);
    assert.equal(html.includes("search-compose-chips"), false);
    assert.equal(html.includes("search-advanced"), false);
    assert.equal(html.includes("More ways to search"), false);
  });
});
