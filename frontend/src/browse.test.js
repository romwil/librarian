import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  BROWSE_EXPORT_COLUMNS,
  BROWSE_LETTERS,
  BROWSE_SORTS,
  applyBrowseFilterPatch,
  browseCountLine,
  browseExportColumnsParam,
  browseExportHref,
  browseFiltersFromSearchParams,
  browseHasActiveFilters,
  browseHeading,
  browseHref,
  browseParamsObject,
  browseQueryParams,
  defaultSortDir,
  formatShelfCount,
  kindCountFromFacets,
  kindShelfTotalLine,
  loadBrowseListColumns,
  mergeFacetSelection,
  normalizeBrowseShelf,
  normalizeExportColumns,
  readBrowseFoldState,
  saveBrowseListColumns,
  sortChangePatch,
  sortDirLabel,
  toggleBrowseFold,
  toggleBrowseListColumn,
} from "./browse.js";
import { coverWashStyle, coverWashUrl } from "./cover.js";

describe("cover wash helpers", () => {
  it("prefers local cover over remote URL", () => {
    assert.equal(
      coverWashUrl({ id: "w1", has_cover: true, cover: "https://example.test/remote.jpg" }),
      "/api/works/w1/cover",
    );
  });

  it("omits remote cover when no local art (P4-MED-02)", () => {
    assert.equal(coverWashUrl({ cover: "https://example.test/a.jpg" }), "");
    assert.equal(coverWashUrl({ cover_url: "https://example.test/b.jpg" }), "");
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
    const shelfId = "ab".repeat(16);
    assert.equal(browseHref({ shelf: shelfId.toUpperCase() }), `/browse?shelf=${shelfId}`);
    assert.equal(browseHref({ shelf: "../../etc/passwd" }), "/browse");
    assert.equal(browseHref({ shelf: "not-a-shelf" }), "/browse");
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
      sort_dir: "asc",
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
      sort_dir: "asc",
      genre: "Science Fiction",
    });
    const shelfId = "cd".repeat(16);
    assert.equal(browseFiltersFromSearchParams(new URLSearchParams(`shelf=${shelfId}`)).shelf, shelfId);
    assert.equal(normalizeBrowseShelf("Favorites"), "favorites");
    assert.equal(normalizeBrowseShelf("favorites'; DROP TABLE shelves--"), "");
  });

  it("defaults sort_dir per sort and honors an explicit override", () => {
    assert.equal(browseFiltersFromSearchParams(new URLSearchParams("sort=year")).sort_dir, "desc");
    assert.equal(browseFiltersFromSearchParams(new URLSearchParams("sort=updated")).sort_dir, "desc");
    assert.equal(browseFiltersFromSearchParams(new URLSearchParams("sort=title")).sort_dir, "asc");
    assert.equal(browseFiltersFromSearchParams(new URLSearchParams()).sort_dir, "asc");
    assert.equal(
      browseFiltersFromSearchParams(new URLSearchParams("sort=year&sort_dir=asc")).sort_dir,
      "asc",
    );
    // Hostile direction values fall back to the sort's default, not a crash.
    assert.equal(
      browseFiltersFromSearchParams(new URLSearchParams("sort=year&sort_dir=sideways")).sort_dir,
      "desc",
    );
    // An unknown sort key falls back to author, same as before.
    assert.equal(browseFiltersFromSearchParams(new URLSearchParams("sort=nope")).sort, "author");
  });
});

describe("browse sort direction defaults", () => {
  it("exposes the four sort keys the command bar offers", () => {
    assert.deepEqual(BROWSE_SORTS, ["author", "title", "updated", "year"]);
  });

  it("picks ascending for author/title, descending for updated/year", () => {
    assert.equal(defaultSortDir("author"), "asc");
    assert.equal(defaultSortDir("title"), "asc");
    assert.equal(defaultSortDir("updated"), "desc");
    assert.equal(defaultSortDir("year"), "desc");
    // Hostile/unknown sort falls back to the author default.
    assert.equal(defaultSortDir("'; DROP TABLE works;--"), "asc");
    assert.equal(defaultSortDir(undefined), "asc");
  });

  it("builds a sort change patch with the matching default direction", () => {
    assert.deepEqual(sortChangePatch("year"), { sort: "year", sort_dir: "desc" });
    assert.deepEqual(sortChangePatch("Title"), { sort: "title", sort_dir: "asc" });
    assert.deepEqual(sortChangePatch("not-a-sort"), { sort: "author", sort_dir: "asc" });
  });

  it("labels sort direction for the toggle button", () => {
    assert.equal(sortDirLabel("asc"), "Ascending");
    assert.equal(sortDirLabel("desc"), "Descending");
    assert.equal(sortDirLabel(""), "Ascending");
    assert.equal(sortDirLabel("DESC"), "Descending");
  });
});

describe("browse query params (shared by the route, the API fetch, and CSV export)", () => {
  it("omits sort_dir when it matches the sort's default", () => {
    assert.equal(browseQueryParams({ sort: "author", sort_dir: "asc" }).toString(), "");
    assert.equal(browseQueryParams({ sort: "updated", sort_dir: "desc" }).toString(), "sort=updated");
  });

  it("writes sort_dir only when it departs from the default", () => {
    const params = browseQueryParams({ sort: "year", sort_dir: "asc" });
    assert.equal(params.get("sort"), "year");
    assert.equal(params.get("sort_dir"), "asc");
  });

  it("ignores a hostile/unknown sort_dir value", () => {
    assert.equal(browseQueryParams({ sort: "title", sort_dir: "sideways" }).has("sort_dir"), false);
  });

  it("carries offset/limit for the API fetch without touching /browse URLs", () => {
    const params = browseQueryParams({ kind: "book" }, { offset: 48, limit: 48 });
    assert.equal(params.get("offset"), "48");
    assert.equal(params.get("limit"), "48");
    assert.equal(browseHref({ kind: "book" }), "/browse?kind=book");
  });

  it("keeps browseHref honoring the shared builder end to end", () => {
    assert.equal(browseHref({ sort: "year", sort_dir: "desc" }), "/browse?sort=year");
    assert.equal(browseHref({ sort: "year", sort_dir: "asc" }), "/browse?sort=year&sort_dir=asc");
  });
});

describe("browse export column building", () => {
  it("validates and dedupes against the canonical column list", () => {
    assert.deepEqual(normalizeExportColumns("title,author,title"), ["title", "author"]);
    assert.deepEqual(normalizeExportColumns(["year", "kind"]), ["year", "kind"]);
    // Canonical order wins over input order.
    assert.deepEqual(normalizeExportColumns(["genre", "title"]), ["title", "genre"]);
  });

  it("drops hostile/unknown entries without throwing", () => {
    assert.deepEqual(
      normalizeExportColumns(["title", "<script>alert(1)</script>", "DROP TABLE works", "", null, undefined]),
      ["title"],
    );
    assert.deepEqual(normalizeExportColumns(null), []);
    assert.deepEqual(normalizeExportColumns(42), []);
  });

  it("omits the columns param for 'all columns' (null, empty, or the full set)", () => {
    assert.equal(browseExportColumnsParam(null), "");
    assert.equal(browseExportColumnsParam([]), "");
    assert.equal(browseExportColumnsParam(BROWSE_EXPORT_COLUMNS), "");
    assert.equal(browseExportColumnsParam([...BROWSE_EXPORT_COLUMNS].reverse()), "");
  });

  it("writes a canonical-order columns param for a real subset", () => {
    assert.equal(browseExportColumnsParam(["author", "title"]), "title,author");
  });

  it("builds the export.csv href with filters and columns together", () => {
    assert.equal(
      browseExportHref({ kind: "book", shelf: "favorites" }, { columns: ["title", "author"] }),
      "/api/browse/export.csv?kind=book&shelf=favorites&columns=title%2Cauthor",
    );
    assert.equal(
      browseExportHref({ kind: "book" }),
      "/api/browse/export.csv?kind=book",
    );
    // No secret/hostile columns reach the URL even on a hostile call.
    assert.equal(
      browseExportHref({}, { columns: ["password", "api_key", "title"] }),
      "/api/browse/export.csv?columns=title",
    );
  });
});

describe("browse list column preference", () => {
  function fakeStorage() {
    const data = {};
    return {
      getItem: (key) => (key in data ? data[key] : null),
      setItem: (key, value) => {
        data[key] = String(value);
      },
    };
  }

  it("defaults to title/author/year/kind and persists a valid change", () => {
    const store = fakeStorage();
    assert.deepEqual(loadBrowseListColumns(store), ["title", "author", "year", "kind"]);
    const saved = saveBrowseListColumns(["series", "title"], store);
    assert.deepEqual(saved, ["title", "series"]);
    assert.deepEqual(loadBrowseListColumns(store), ["title", "series"]);
  });

  it("falls back to defaults when storage holds garbage", () => {
    const store = { getItem: () => "{not json", setItem: () => {} };
    assert.deepEqual(loadBrowseListColumns(store), ["title", "author", "year", "kind"]);
  });

  it("toggles one column without ever dropping to zero", () => {
    const store = fakeStorage();
    saveBrowseListColumns(["title"], store);
    const removed = toggleBrowseListColumn(["title"], "title", store);
    // Only column left — toggle refuses to empty the list.
    assert.deepEqual(removed, ["title"]);
    const added = toggleBrowseListColumn(["title"], "author", store);
    assert.deepEqual(added, ["title", "author"]);
  });

  it("ignores an unknown column key", () => {
    assert.deepEqual(toggleBrowseListColumn(["title"], "nope"), ["title"]);
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
    assert.equal(browseHeading({ shelf: "favorites" }), "Favorites");
    assert.equal(browseHeading({ shelf: "ab".repeat(16) }, "Beach"), "Beach");
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
