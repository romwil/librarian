import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  emptyHallCopy,
  emptyReviewCopy,
  humanError,
  searchStatusLine,
  setupComplete,
  setupStepComplete,
} from "./copy.js";

describe("reading room copy", () => {
  it("turns login failures into door copy", () => {
    assert.match(humanError({ status: 401, message: "Invalid username or password" }, "login"), /join link/);
    assert.match(humanError({ status: 429, message: "Too many requests" }, "login"), /Wait a minute/);
  });

  it("turns fetch failures into a running-check, without hiding a real 401", () => {
    const unreachable = /Can.?t reach Librarian/;
    assert.match(humanError(new TypeError("Failed to fetch"), "login"), unreachable);
    assert.match(humanError({ message: "NetworkError when attempting to fetch resource" }), unreachable);
    assert.match(humanError({ message: "Load failed" }), unreachable);
    assert.match(humanError({ status: 401, message: "Failed to fetch" }, "login"), /join link/);
  });

  it("turns indexer and SAB failures into Settings guidance", () => {
    assert.match(humanError("NZBFinder api_token is not configured"), /NZBFinder token/);
    assert.match(humanError("NZBFinder returned non-JSON"), /could not read/);
    assert.match(humanError("SABnzbd API key is not configured"), /API key/);
  });

  it("does not let the nzbfinder catch-all overwrite a token-missing message on a second pass", () => {
    const tokenMissing = humanError("NZBFinder api_token is not configured");
    assert.equal(tokenMissing, "Beyond the shelves needs an NZBFinder token in Settings.");
    assert.equal(humanError(tokenMissing), tokenMissing);
  });

  it("summarizes a search so the page is not a quiet event", () => {
    assert.equal(searchStatusLine({ q: "" }), "Type a title, author, ISBN, or series.");
    assert.match(
      searchStatusLine({ q: "stephen king", phase: "local" }),
      /searched stephen king · looking on the shelves/,
    );
    assert.equal(
      searchStatusLine({ q: "stephen king", kind: "book", localCount: 2, beyondCount: 11, phase: "done" }),
      "searched stephen king · book · 2 on shelves · 11 beyond",
    );
    assert.match(searchStatusLine({ q: "dune", localCount: 1, phase: "beyond_error" }), /beyond could not be reached/);
  });

  it("keeps Hall and Review empty states human", () => {
    assert.equal(emptyHallCopy({ owner: true }).title, "Open the stacks");
    assert.equal(emptyHallCopy({ configured: true }).title, "The shelves are still bare");
    assert.match(emptyReviewCopy(), /bagging area is empty/);
  });

  it("treats Settings as configured only when SAB, indexer, and books root exist", () => {
    assert.equal(setupComplete({}), false);
    assert.equal(
      setupComplete({
        sabnzbd_url: "http://downloader.sl:8080",
        sabnzbd_api_key_set: true,
        nzbfinder_api_token_set: true,
        books_root: "/data/books",
      }),
      true,
    );
    assert.equal(setupStepComplete({ sabnzbd_url: "http://x", sabnzbd_api_key_set: true }, 0), true);
    assert.equal(setupStepComplete({ complete_root: "/downloads" }, 3), true);
  });
});
