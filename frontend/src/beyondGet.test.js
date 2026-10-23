import assert from "node:assert/strict";
import { mkdirSync, readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, it } from "node:test";
import * as esbuild from "esbuild";
import {
  askHitFromItem,
  beyondGetLabel,
  beyondGetPhase,
  saveBeyondGet,
  wantedBodyFromHit,
} from "./beyondGet.js";

const frontendRoot = fileURLToPath(new URL("..", import.meta.url));
const srcRoot = dirname(fileURLToPath(import.meta.url));

async function loadCatalogVerb() {
  const cache = join(frontendRoot, "node_modules/.cache");
  mkdirSync(cache, { recursive: true });
  const outfile = join(cache, "librarian-catalog-verb-test.mjs");
  await esbuild.build({
    absWorkingDir: frontendRoot,
    entryPoints: ["src/components/CatalogVerb.jsx"],
    bundle: true,
    format: "esm",
    outfile,
    jsx: "automatic",
    platform: "node",
    packages: "external",
  });
  return (await import(pathToFileURL(outfile).href)).default;
}

const hit = {
  title: "Scientific American 2026-10",
  guid: "guid-scientific",
  kind: "magazine",
  author: "",
  host_id: "nzbfinder",
};

describe("beyond Get save", () => {
  it("does not treat an indexer id as a catalog work_id", () => {
    const body = wantedBodyFromHit({ ...hit, id: "not-a-work", work_id: "" });
    assert.equal(body.work_id, "");
    assert.equal(body.title, "Scientific American 2026-10");
    assert.equal(body.kind, "magazine");
    assert.equal(askHitFromItem(hit).guid, "guid-scientific");
  });

  it("files Wanted then an Asked slip when the hit has a guid", async () => {
    const calls = [];
    const result = await saveBeyondGet(hit, {
      addWanted: async (body) => {
        calls.push(["add", body]);
        return { item: { id: "w1", status: "wanted", title: body.title } };
      },
      askWanted: async (id, asked) => {
        calls.push(["ask", id, asked]);
        return { item: { id, status: "asked" }, outcome: "hit" };
      },
    });
    assert.equal(calls[0][0], "add");
    assert.equal(calls[1][0], "ask");
    assert.equal(calls[1][1], "w1");
    assert.equal(calls[1][2].guid, "guid-scientific");
    assert.equal(result.jobStatus, "asked");
    assert.equal(result.wanted.status, "asked");
  });

  it("stays saved when the same Wanted row is already asked", async () => {
    let asked = 0;
    const result = await saveBeyondGet(hit, {
      addWanted: async () => ({ item: { id: "w1", status: "asked" } }),
      askWanted: async () => {
        asked += 1;
        throw new Error("should not ask twice");
      },
    });
    assert.equal(asked, 0);
    assert.equal(result.jobStatus, "asked");
  });

  it("surfaces add failures instead of swallowing them", async () => {
    await assert.rejects(
      () =>
        saveBeyondGet(hit, {
          addWanted: async () => {
            throw new Error("Title or ISBN is required");
          },
        }),
      /Title or ISBN is required/,
    );
  });

  it("names idle, getting, and queued", () => {
    assert.equal(beyondGetLabel(beyondGetPhase({})), "Get");
    assert.equal(beyondGetLabel(beyondGetPhase({ busy: true })), "Getting…");
    assert.equal(beyondGetLabel(beyondGetPhase({ queued: true, busy: true })), "Queued");
  });
});

describe("CatalogVerb Get", () => {
  it("shows Get, then Getting…, then Queued, and restores Get with an error", async () => {
    const CatalogVerb = await loadCatalogVerb();
    const getView = { show: true, status: "Not on the shelf", verb: "Get", canAdd: true };
    const idle = renderToStaticMarkup(createElement(CatalogVerb, { view: getView }));
    assert.match(idle, />Get</);
    assert.equal(idle.includes("Getting"), false);

    const getting = renderToStaticMarkup(createElement(CatalogVerb, { view: getView, busy: true }));
    assert.match(getting, />Getting…</);
    assert.match(getting, /disabled/);
    assert.match(getting, /aria-busy="true"/);

    const queued = renderToStaticMarkup(
      createElement(CatalogVerb, {
        view: { show: true, status: "Asked", verb: "Queued", canAdd: false },
      }),
    );
    assert.match(queued, />Queued</);
    assert.match(queued, />Asked</);
    assert.match(queued, /disabled/);
    assert.equal(queued.includes(">Get<"), false);

    const failed = renderToStaticMarkup(
      createElement(CatalogVerb, { view: getView, error: "The indexer token was refused." }),
    );
    assert.match(failed, />Get</);
    assert.match(failed, /role="alert"/);
    assert.match(failed, /The indexer token was refused/);
  });
});

describe("Search beyond Get wiring", () => {
  it("Search Beyond rails save with Get, and idle Search shows Discover", () => {
    const searchSrc = readFileSync(join(srcRoot, "pages/SearchPage.jsx"), "utf8");
    const cardSrc = readFileSync(join(srcRoot, "components/CoverCard.jsx"), "utf8");
    const peekSrc = readFileSync(join(srcRoot, "components/WorkPeek.jsx"), "utf8");
    assert.match(searchSrc, /onRequest=\{request\}/);
    assert.match(searchSrc, /saveBeyondGet/);
    assert.match(searchSrc, /data-testid="discover-panel"/);
    assert.match(searchSrc, /advancedOpen/);
    assert.match(searchSrc, /findKindOptions/);
    assert.equal(searchSrc.includes("api.requestItem"), false);
    assert.match(cardSrc, /getBeyond/);
    assert.match(cardSrc, /saveBeyondGet/);
    assert.match(cardSrc, /setGetError/);
    assert.match(peekSrc, /getBeyond/);
    assert.match(peekSrc, /saveBeyondGet/);
  });
});
