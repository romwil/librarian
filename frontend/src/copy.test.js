import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  DISCOVER_CTA,
  FIND_BEYOND_CTA,
  ADD_TO_LIBRARY_LEDE,
  canPromoteIncomingMusic,
  emptyHallCopy,
  emptyReviewCopy,
  findStatusLine,
  humanError,
  peekMediaNote,
  queueNeedsYouHelp,
  searchStatusLine,
  setupComplete,
  setupStepComplete,
} from "./copy.js";

describe("reading room copy", () => {
  it("explains Needs you on Queue", () => {
    assert.match(queueNeedsYouHelp(), /Needs you means Review/);
    assert.match(queueNeedsYouHelp(), /files are here/);
    assert.match(queueNeedsYouHelp(), /Open Review/);
  });

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

  it("summarizes a local search so the page is not a quiet event", () => {
    assert.equal(searchStatusLine({ q: "" }), "Type a title, author, ISBN, or series.");
    assert.equal(searchStatusLine({ q: "", kind: "music" }), "Type an artist or album.");
    assert.equal(searchStatusLine({ q: "", kind: "comic" }), "Type a series or issue.");
    assert.equal(searchStatusLine({ q: "", kind: "audiobook" }), "Type a title or author.");
    assert.equal(searchStatusLine({ q: "", kind: "book" }), "Type a title, author, or ISBN.");
    assert.match(
      searchStatusLine({ q: "stephen king", phase: "local" }),
      /searched stephen king · looking on the shelves/,
    );
    assert.equal(
      searchStatusLine({ q: "stephen king", kind: "book", localCount: 2, phase: "done" }),
      "searched stephen king · book · 2 on shelves",
    );
    assert.match(searchStatusLine({ q: "dune", localCount: 1, phase: "error" }), /the shelves could not be searched/);
  });

  it("summarizes Find beyond the shelves without mixing in local hits", () => {
    assert.equal(FIND_BEYOND_CTA, "Find beyond the shelves");
    assert.equal(DISCOVER_CTA, "What's trending");
    assert.equal(findStatusLine({ q: "" }), "Peruse trending on the indexers, or name a title to find.");
    assert.match(findStatusLine({ q: "dune", phase: "beyond" }), /finding dune · looking beyond/);
    assert.equal(findStatusLine({ q: "dune", kind: "book", beyondCount: 11, phase: "done" }), "finding dune · book · 11 beyond");
    assert.match(findStatusLine({ q: "dune", phase: "beyond_error" }), /beyond could not be reached/);
  });

  it("keeps Hall and Review empty states human", () => {
    assert.equal(emptyHallCopy({ owner: true }).title, "Open the stacks");
    assert.equal(emptyHallCopy({ configured: true }).title, "The shelves are still bare");
    assert.match(emptyReviewCopy(), /Holds desk is empty/);
  });

  it("describes Add to the shelves without an import wizard", () => {
    assert.match(ADD_TO_LIBRARY_LEDE, /\/data/);
    assert.doesNotMatch(ADD_TO_LIBRARY_LEDE, /wizard/i);
  });

  it("explains a peek with no file instead of offering a dead Open", () => {
    assert.equal(peekMediaNote({ id: "w1" }, { canDownload: true, ready: true }), "");
    assert.equal(peekMediaNote({ id: "w1" }, { ready: false }), "");
    assert.equal(
      peekMediaNote({ id: "w1", review_reason: "no_payload", review_state: "needs_review" }, { ready: true }),
      "Still in Review — there isn’t a file to open yet.",
    );
    assert.equal(peekMediaNote({ id: "w1" }, { ready: true }), "This volume isn’t on the shelf as a file yet.");
    assert.equal(
      peekMediaNote({ id: "w1", kind: "music", music_state: "incoming" }, { ready: true }),
      "This volume isn’t on the shelf as a file yet.",
    );
  });

  it("offers peek Promote only to keepers on incoming music", () => {
    const incoming = { kind: "music", music_state: "incoming" };
    assert.equal(canPromoteIncomingMusic(incoming, "owner"), true);
    assert.equal(canPromoteIncomingMusic(incoming, "op"), true);
    assert.equal(canPromoteIncomingMusic(incoming, "reader"), false);
    assert.equal(canPromoteIncomingMusic({ kind: "music", music_state: "promoted" }, "owner"), false);
    assert.equal(canPromoteIncomingMusic({ kind: "book", music_state: "incoming" }, "owner"), false);
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

  it("turns LLM rate limits into household copy", () => {
    assert.match(humanError("LLM HTTP 429"), /rate-limited|Wait a minute/i);
    assert.match(
      humanError(
        "The reading room’s language model is rate-limited right now. Wait a minute, then try again — shelves and Find still work without it.",
      ),
      /rate-limited/i,
    );
  });

  it("turns Errno 13 cover writes into household enrich copy", () => {
    assert.match(
      humanError(`[Errno 13] Permission denied: "/data/media/library/books/Author/Title/cover.jpg"`),
      /shelf folder is locked|cover cache/i,
    );
  });

  it("turns bare Internal Server Error / empty 500 into filing copy", () => {
    assert.match(humanError({ status: 500, message: "Internal Server Error" }), /filing this slip|Librarian logs/i);
    assert.match(humanError({ status: 500, message: "" }), /filing this slip|Librarian logs/i);
    assert.match(
      humanError({ status: 500, message: "Internal Server Error", statusText: "Internal Server Error" }),
      /filing this slip|Librarian logs/i,
    );
    assert.doesNotMatch(humanError({ status: 500, message: "Internal Server Error" }), /Internal Server Error/);
  });

  it("keeps Apply shelf PermissionError guidance", () => {
    const locked =
      "Couldn't write into the library shelf — a folder is locked for the lamp " +
      "(PUID ownership under the books root). Fix permissions, then Apply again.";
    assert.equal(humanError({ status: 400, message: locked }), locked);
    assert.match(
      humanError({ status: 500, message: `[Errno 13] Permission denied: "/data/media/library/books/Author/Title"` }),
      /library shelf|PUID/i,
    );
  });

  it("keeps Review Apply collision guidance instead of masking it", () => {
    const collision =
      "A file already exists at the library destination. " +
      "Apply will not overwrite — change the title/folder, or Skip to keep the shelf copy.";
    assert.equal(humanError(collision), collision);
    assert.equal(
      humanError({
        status: 400,
        message:
          "A file already exists at the library destination. Apply will not overwrite. " +
          "Change title, author, series, or folder so the destination path is free, or Skip to keep what is on the shelf.",
      }),
      "A file already exists at the library destination. Apply will not overwrite. " +
        "Change title, author, series, or folder so the destination path is free, or Skip to keep what is on the shelf.",
    );
  });
});

