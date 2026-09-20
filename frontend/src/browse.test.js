import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  BROWSE_LETTERS,
  applyBrowseFilterPatch,
  browseCountLine,
  browseFiltersFromSearchParams,
  browseHasActiveFilters,
  browseHeading,
  browseHref,
  browseParamsObject,
  formatShelfCount,
  kindCountFromFacets,
  kindShelfTotalLine,
  mergeFacetSelection,
  readBrowseFoldState,
  toggleBrowseFold,
} from "./browse.js";
import { coverWashStyle, coverWashUrl } from "./cover.js";

describe("cover wash helpers", () => {
  it("prefers local cover over remote URL", () => {
    assert.equal(
      coverWashUrl({ id: "w1", has_cover: true, cover: "https://example.test/remote.jpg" }),
      "/api/works/w1/cover",
    );
  });

  it("falls back to remote cover when no local art", () => {
    assert.equal(coverWashUrl({ cover: "https://example.test/a.jpg" }), "https://example.test/a.jpg");
    assert.equal(coverWashUrl({ cover_url: "https://example.test/b.jpg" }), "https://example.test/b.jpg");
  });

  it("returns no wash style without art", () => {
    assert.equal(coverWashUrl({}), "");
    assert.equal(coverWashStyle({}), undefined);
    assert.equal(coverWashStyle({ has_cover: true, id: "w2" })["--work-wash"], 'url("/api/works/w2/cover")');
  });
});

describe("kind shelf totals", () => {
  it("formats household kind totals", () => {
    assert.equal(formatShelfCount(1234), "1,234");
    assert.equal(kindShelfTotalLine("book", 1234), "1,234 books on the shelves");
    assert.equal(kindShelfTotalLine("book", 1), "1 book on the shelves");
    assert.equal(kindShelfTotalLine("audiobook", 56), "56 audiobooks");
    assert.equal(kindShelfTotalLine("comic", 0), "0 comics on the shelves");
    assert.equal(kindShelfTotalLine("", 10), "");
    assert.equal(kindShelfTotalLine("book", null), "");
  });

  it("reads kind counts from facets or hall maps", () => {
    assert.equal(kindCountFromFacets({ kinds: [{ kind: "book", count: 12 }, { kind: "comic", count: 3 }] }, "book"), 12);
    assert.equal(kindCountFromFacets({ kinds: [{ kind: "book", count: 12 }] }, "audiobook"), 0);
    assert.equal(kindCountFromFacets({ book: 99, audiobook: 56 }, "audiobook"), 56);
    assert.equal(kindCountFromFacets(null, "book"), null);
  });

  it("builds stacks count lines for kind, favorites, and all", () => {
    assert.equal(browseCountLine({ loading: true }), "Opening the stacks…");
    assert.equal(browseCountLine({ kind: "book", total: 1234 }), "1,234 books on the shelves");
    assert.equal(browseCountLine({ kind: "audiobook", total: 56 }), "56 audiobooks");
    assert.equal(browseCountLine({ shelf: "favorites", total: 2 }), "2 favorites on the shelves");
    assert.equal(browseCountLine({ total: 10 }), "10 on the shelves");
    assert.equal(browseCountLine({ total: 0 }), "Nothing on the shelves yet");
  });
});

describe("browse href helpers", () => {
  it("builds stacks URLs for author kind series favorites", () => {
    assert.equal(browseHref(), "/browse");
    assert.equal(browseHref({ kind: "book" }), "/browse?kind=book");
    assert.equal(browseHref({ author: "Stephen King" }), "/browse?author=Stephen+King");
    assert.equal(browseHref({ letter: "s" }), "/browse?letter=S");
    assert.equal(browseHref({ series: "Dune" }), "/browse?series=Dune");
    assert.equal(browseHref({ shelf: "favorites" }), "/browse?shelf=favorites");
    assert.equal(browseHref({ genre: "Science Fiction" }), "/browse?genre=Science+Fiction");
  });

  it("parses browse search params", () => {
    const params = new URLSearchParams("kind=book&letter=a&shelf=favorites&sort=title");
    assert.deepEqual(browseFiltersFromSearchParams(params), {
      kind: "book",
      author: "",
      letter: "A",
      series: "",
      shelf: "favorites",
      sort: "title",
      genre: "",
    });
    assert.ok(BROWSE_LETTERS.includes("#"));
    assert.ok(BROWSE_LETTERS.includes("Z"));
  });

  it("parses deep-linked series and genre", () => {
    const params = new URLSearchParams("kind=book&series=Archive+Historical&genre=Science+Fiction");
    assert.deepEqual(browseFiltersFromSearchParams(params), {
      kind: "book",
      author: "",
      letter: "",
      series: "Archive Historical",
      shelf: "",
      sort: "author",
      genre: "Science Fiction",
    });
  });
});

describe("browse facet selection helpers", () => {
  it("prepends an orphaned selected series so it stays clearable", () => {
    const rows = [
      { name: "Alex Cross", count: 30 },
      { name: "Dune", count: 12 },
    ];
    const merged = mergeFacetSelection(rows, "Archive Historical", { limit: 16 });
    assert.equal(merged[0].name, "Archive Historical");
    assert.equal(merged[0].count, null);
    assert.equal(merged[1].name, "Alex Cross");
    assert.equal(merged.length, 3);
  });

  it("moves an in-list selection to the front within the limit", () => {
    const rows = Array.from({ length: 20 }, (_, i) => ({ name: `Series ${i}`, count: 20 - i }));
    const merged = mergeFacetSelection(rows, "Series 18", { limit: 16 });
    assert.equal(merged[0].name, "Series 18");
    assert.equal(merged.length, 16);
    assert.ok(merged.every((row) => row.name !== "Series 19"));
  });

  it("clears kind-scoped facets when kind changes", () => {
    const current = {
      kind: "book",
      author: "Ada",
      letter: "A",
      series: "Archive Historical",
      genre: "Science Fiction",
      shelf: "favorites",
      sort: "title",
    };
    assert.deepEqual(applyBrowseFilterPatch(current, { kind: "comic" }), {
      kind: "comic",
      author: "",
      letter: "",
      series: "",
      genre: "",
      shelf: "favorites",
      sort: "title",
    });
    assert.deepEqual(applyBrowseFilterPatch(current, { series: "" }).series, "");
    assert.equal(applyBrowseFilterPatch(current, { kind: "book" }).series, "Archive Historical");
  });

  it("builds headings and clear-filter visibility from all active facets", () => {
    assert.equal(browseHeading({}), "The stacks");
    assert.equal(
      browseHeading({
        kind: "book",
        series: "Archive Historical",
        genre: "Science Fiction",
      }),
      "book · Archive Historical · Science Fiction",
    );
    assert.equal(browseHasActiveFilters({ genre: "Science Fiction" }), true);
    assert.equal(browseHasActiveFilters({ sort: "title" }), false);
  });

  it("replaces search params without orphaning cleared facets", () => {
    const next = applyBrowseFilterPatch(
      {
        kind: "book",
        series: "Archive Historical",
        genre: "Science Fiction",
        author: "",
        letter: "",
        shelf: "",
        sort: "author",
      },
      { series: "" },
    );
    assert.deepEqual(browseParamsObject(next), {
      kind: "book",
      genre: "Science Fiction",
    });
    assert.deepEqual(browseParamsObject(applyBrowseFilterPatch(next, { genre: "" })), {
      kind: "book",
    });
  });
});

describe("browse facet folds", () => {
  it("defaults author/series/genre collapsed and persists toggles", () => {
    const store = {
      data: {},
      getItem(key) {
        return this.data[key] ?? null;
      },
      setItem(key, value) {
        this.data[key] = String(value);
      },
    };
    assert.deepEqual(readBrowseFoldState(store), { author: false, series: false, genre: false });
    const opened = toggleBrowseFold(readBrowseFoldState(store), "author", store);
    assert.equal(opened.author, true);
    assert.deepEqual(readBrowseFoldState(store), opened);
    const closed = toggleBrowseFold(opened, "author", store);
    assert.equal(closed.author, false);
  });
});
