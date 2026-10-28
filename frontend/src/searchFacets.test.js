import assert from "node:assert/strict";
import { describe, it } from "vitest";
import { applySearchFacets, countSearchFacets, yearFacetEntries } from "./searchFacets.js";

const result = {
  local: [
    { title: "Dune", kind: "book", year: 1965 },
    { title: "Saga", kind: "comic", year: 2012 },
  ],
  beyond: [{ title: "Neuromancer", kind: "book", year: 1984 }],
  public_domain: [{ title: "Pride", kind: "book", year: 1813 }],
};

describe("search facets from the current result set", () => {
  it("counts format, where, and year without recrawling", () => {
    const counts = countSearchFacets(result);
    assert.equal(counts.formats.book, 3);
    assert.equal(counts.formats.comic, 1);
    assert.equal(counts.formats.audiobook, 0);
    assert.equal(counts.where.shelf, 2);
    assert.equal(counts.where.beyond, 1);
    assert.equal(counts.where.public_domain, 1);
    assert.equal(counts.years["1965"], 1);
    assert.deepEqual(
      yearFacetEntries(counts.years).map(([year]) => year),
      ["2012", "1984", "1965", "1813"],
    );
  });

  it("filters the current rows by format, where, and year", () => {
    const books = applySearchFacets(result, { format: "book" });
    assert.equal(books.local.length, 1);
    assert.equal(books.beyond.length, 1);
    assert.equal(books.public_domain.length, 1);
    const shelf = applySearchFacets(result, { where: "shelf" });
    assert.equal(shelf.local.length, 2);
    assert.equal(shelf.beyond.length, 0);
    const year = applySearchFacets(result, { year: "1965" });
    assert.equal(year.local[0].title, "Dune");
    assert.equal(year.beyond.length, 0);
  });
});
