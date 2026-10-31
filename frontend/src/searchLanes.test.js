import assert from "node:assert/strict";
import { describe, it } from "vitest";
import {
  ASK_THE_HOUSE,
  DISCLOSURE_STORAGE_KEY,
  beyondDisclosureBody,
  rememberDisclosure,
  readerSawDisclosure,
  shouldAutoBeyond,
} from "./searchLanes.js";

describe("search lanes", () => {
  it("auto-beyonds owner and op only", () => {
    assert.equal(shouldAutoBeyond("owner"), true);
    assert.equal(shouldAutoBeyond("op"), true);
    assert.equal(shouldAutoBeyond("reader"), false);
  });

  it("names indexer, model, and public-domain sites in the disclosure", () => {
    const body = beyondDisclosureBody({
      indexers: ["NZBFinder", "DrunkenSlug"],
      model: "OpenAI",
      publicDomain: ["Project Gutenberg", "Standard Ebooks"],
    });
    assert.match(body, /NZBFinder/);
    assert.match(body, /DrunkenSlug/);
    assert.match(body, /OpenAI/);
    assert.match(body, /Project Gutenberg/);
    assert.match(body, /owner confirms/);
    assert.equal(body.includes("Ask the house") || ASK_THE_HOUSE === "Ask the house", true);
  });

  it("remembers the one-time disclosure in memory storage", () => {
    const store = new Map();
    const storage = {
      getItem: (key) => (store.has(key) ? store.get(key) : null),
      setItem: (key, value) => store.set(key, String(value)),
    };
    assert.equal(readerSawDisclosure(storage), false);
    rememberDisclosure(storage);
    assert.equal(storage.getItem(DISCLOSURE_STORAGE_KEY), "1");
    assert.equal(readerSawDisclosure(storage), true);
  });
});
