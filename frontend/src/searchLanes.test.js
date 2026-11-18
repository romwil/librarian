import assert from "node:assert/strict";
import { describe, it } from "vitest";
import {
  ASK_THE_HOUSE,
  DISCLOSURE_STORAGE_KEY,
  beyondDisclosureBody,
  canSearchBeyond,
  rememberDisclosure,
  readerSawDisclosure,
} from "./searchLanes.js";

describe("search lanes", () => {
  it("offers beyond to owner, op, and trusted readers — never auto", () => {
    assert.equal(canSearchBeyond("owner"), true);
    assert.equal(canSearchBeyond("op"), true);
    assert.equal(canSearchBeyond("reader"), false);
    assert.equal(canSearchBeyond({ role: "reader" }), false);
    assert.equal(canSearchBeyond({ role: "reader", trusted_acquire: true }), true);
    assert.equal(canSearchBeyond({ role: "owner", trusted_acquire: false }), true);
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
