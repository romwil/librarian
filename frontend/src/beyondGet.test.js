// @vitest-environment jsdom
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { createElement } from "react";
import { render, screen } from "@testing-library/react";
import { describe, it } from "vitest";
import CatalogVerb from "./components/CatalogVerb.jsx";
import { askHitFromItem, beyondGetLabel, beyondGetPhase, saveBeyondGet, wantedBodyFromHit } from "./beyondGet.js";

const srcRoot = dirname(fileURLToPath(import.meta.url));

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
    assert.equal(calls[0][1].hit.guid, "guid-scientific");
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
  it("shows Get, then Getting…, then Queued, and restores Get with an error", () => {
    const getView = { show: true, status: "Not on the shelf", verb: "Get", canAdd: true };
    const { rerender } = render(createElement(CatalogVerb, { view: getView }));
    const idle = screen.getByRole("button", { name: "Get" });
    assert.equal(idle.disabled, false);
    assert.equal(screen.queryByText("Getting…"), null);

    rerender(createElement(CatalogVerb, { view: getView, busy: true }));
    const getting = screen.getByRole("button", { name: "Getting…" });
    assert.equal(getting.disabled, true);
    assert.equal(getting.getAttribute("aria-busy"), "true");

    rerender(createElement(CatalogVerb, { view: { show: true, status: "Asked", verb: "Queued", canAdd: false } }));
    assert.equal(screen.getByRole("button", { name: "Queued" }).disabled, true);
    assert.ok(screen.getByText("Asked"));
    assert.equal(screen.queryByRole("button", { name: "Get" }), null);

    rerender(createElement(CatalogVerb, { view: getView, error: "The indexer token was refused." }));
    assert.ok(screen.getByRole("button", { name: "Get" }));
    assert.match(screen.getByRole("alert").textContent, /The indexer token was refused/);
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
