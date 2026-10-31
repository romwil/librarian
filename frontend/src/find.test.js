import assert from "node:assert/strict";
import { describe, it } from "vitest";
import {
  buildFindSearchParams,
  bestsellersFromSearchParams,
  bestsellersHref,
  composeSearchQuery,
  DISCOVER_EBOOK_CAT,
  DISCOVER_PAGE_SIZE,
  discoverCatFromSearchParams,
  discoverFeedRequest,
  discoverHref,
  findFieldsFromSearchParams,
  findHref,
  gapFindFields,
  catalogGapFanoutQueries,
  isCatalogGapQuery,
  nytHitFindHref,
  nytHitHref,
  rankBeyondByCompleteness,
  groupDiscoverCategories,
  groupDiscoverRails,
  pruneFieldsForKind,
  requestBodyFromHit,
  searchHref,
  searchLadder,
  searchRequestQuery,
  shouldShowDiscover,
  findKindOptions,
  visibleFindFields,
  beyondHostName,
} from "./find.js";

describe("Find query builder", () => {
  it("builds /search with q and kind", () => {
    assert.equal(findHref({ q: "dune", kind: "book" }), "/search?q=dune&kind=book");
  });

  it("adds advanced author, title, and isbn when used", () => {
    assert.equal(
      findHref({ q: "dune", kind: "book", author: "Herbert", title: "Dune", isbn: "9780441172719" }),
      "/search?q=dune&kind=book&author=Herbert&title=Dune&isbn=9780441172719",
    );
  });

  it("leaves /search empty when there is no query", () => {
    assert.equal(findHref({}), "/search");
    assert.equal(findHref({ q: "  ", kind: "" }), "/search");
  });

  it("shows Discover when Find has no query", () => {
    assert.equal(shouldShowDiscover({}), true);
    assert.equal(shouldShowDiscover({ q: "dune" }), false);
    assert.equal(shouldShowDiscover({ kind: "comic" }), true);
    assert.equal(discoverHref({ kind: "comic" }), "/search?kind=comic");
    assert.equal(discoverHref({}), "/search");
    assert.equal(findKindOptions(false).some(([value]) => value === "movie"), false);
    assert.equal(findKindOptions(true).some(([value]) => value === "movie"), false);
  });

  it("pages ebook trending and does not follow a kind chip", () => {
    assert.equal(DISCOVER_EBOOK_CAT, "7020");
    assert.equal(DISCOVER_PAGE_SIZE, 12);
    assert.deepEqual(discoverFeedRequest(0), { cat: "7020", limit: 12 });
    assert.deepEqual(discoverFeedRequest(1), { cat: "7020", limit: 12, offset: 12 });
    assert.deepEqual(discoverFeedRequest(2), { cat: "7020", limit: 12, offset: 24 });
    assert.equal(discoverFeedRequest(-1).kind, undefined);
    assert.equal(discoverFeedRequest("comic").offset, undefined);
    assert.equal(discoverFeedRequest(0).kind, undefined);
  });

  it("builds Discover category browse hrefs from cat id", () => {
    assert.equal(discoverHref({ discover: "7030" }), "/search?discover=7030");
    assert.equal(discoverHref({ discover: "7030", kind: "comic" }), "/search?discover=7030&kind=comic");
    assert.equal(discoverHref({ cat: "7010", kind: "magazine" }), "/search?discover=7010&kind=magazine");
    assert.equal(discoverHref({}), "/search");
    assert.equal(discoverCatFromSearchParams(new URLSearchParams("discover=7030&kind=comic")), "7030");
    assert.equal(discoverCatFromSearchParams(new URLSearchParams("cat=7010")), "7010");
    assert.equal(discoverCatFromSearchParams(new URLSearchParams("kind=comic")), "");
  });

  it("groups Discover items onto one rail per category", () => {
    const rails = groupDiscoverRails(
      [
        { title: "Issue 1", category: "7010", category_name: "Magazines" },
        { title: "Issue 2", category: "7010" },
        { title: "Comic 1", category: "7030", category_name: "Comics" },
      ],
      [{ id: "7010", name: "Magazines" }],
    );
    assert.equal(rails.length, 2);
    assert.equal(rails[0].title, "Magazines");
    assert.equal(rails[0].items.length, 2);
    assert.equal(rails[1].title, "Comics");
  });

  it("groups Discover chips under Newznab parents and dedupes ids", () => {
    const groups = groupDiscoverCategories([
      { id: "7030", name: "Comics", kind: "comic", parent_id: "7000", parent_name: "Books" },
      { id: "7010", name: "Magazines", kind: "magazine", parent_id: "7000", parent_name: "Books" },
      { id: "3030", name: "Audiobook", kind: "audiobook", parent_id: "3000", parent_name: "Audio" },
      { id: "7030", name: "Comics", kind: "comic", parent_id: "7000", parent_name: "Books" },
      { id: "7060", name: "Foreign", kind: "book", parent_id: "7000", parent_name: "Books" },
    ]);
    assert.deepEqual(
      groups.map((g) => [g.id, g.name, g.categories.map((c) => c.id)]),
      [
        ["3000", "Audio", ["3030"]],
        ["7000", "Books", ["7030", "7010", "7060"]],
      ],
    );
  });

  it("still groups quieter library feeds when extras are off", () => {
    const groups = groupDiscoverCategories([
      { id: "3010", name: "MP3", kind: "music", parent_id: "3000", parent_name: "Audio" },
      { id: "7020", name: "Ebook", kind: "book", parent_id: "7000", parent_name: "Books" },
    ]);
    assert.equal(groups.length, 2);
    assert.equal(groups[0].name, "Audio");
    assert.equal(groups[1].name, "Books");
  });

  it("only uses the joined prefill to tell whether Find has a query", () => {
    assert.equal(composeSearchQuery({ q: "dune", author: "Herbert" }), "dune Herbert");
    assert.equal(composeSearchQuery({}), "");
  });

  it("sends one precise query, not every known field ANDed together", () => {
    const prefill = { kind: "book", title: "Dune", author: "Frank Herbert", isbn: "9780441172719", year: "1965" };
    assert.equal(searchRequestQuery(prefill), "Dune");
    assert.equal(searchRequestQuery({ ...prefill, q: "dune herbert" }), "dune herbert");
    assert.equal(searchRequestQuery({ kind: "comic", series: "Saga", issue: "54" }), "Saga 54");
    assert.equal(searchRequestQuery({ kind: "music", artist: "Queen", album: "Jazz", year: "1978" }), "Jazz");
    assert.equal(searchRequestQuery({ kind: "", title: "Dune" }), "Dune");
    assert.notEqual(searchRequestQuery(prefill), composeSearchQuery(prefill));
  });

  it("walks the book ladder: ISBN alone, title alone, then title and author", () => {
    const ladder = searchLadder({
      kind: "book",
      title: "Dune",
      author: "Frank Herbert",
      isbn: "978-0-441-17271-9",
      year: "1965",
    });
    assert.deepEqual(
      ladder.map((rung) => [rung.rung, rung.q, rung.isbn, rung.title, rung.author, rung.year]),
      [
        ["isbn", "9780441172719", "9780441172719", "", "", ""],
        ["title", "Dune", "", "Dune", "", ""],
        ["title_author", "Dune Frank Herbert", "", "Dune", "Frank Herbert", ""],
      ],
    );
  });

  it("skips a fake ISBN and never exceeds three rungs", () => {
    const ladder = searchLadder({ kind: "audiobook", title: "Dune", author: "Herbert", isbn: "9780441172710" });
    assert.deepEqual(ladder.map((rung) => rung.rung), ["title", "title_author"]);
    for (const kind of ["book", "audiobook", "magazine", "comic", "music", ""]) {
      const rungs = searchLadder({
        kind,
        q: "x",
        title: "T",
        author: "A",
        isbn: "9780441172719",
        series: "S",
        issue: "1",
        artist: "R",
        album: "L",
        year: "2020",
      });
      assert.ok(rungs.length <= 3, kind);
    }
  });

  it("walks comic, magazine, and music ladders one field at a time", () => {
    assert.deepEqual(
      searchLadder({ kind: "comic", series: "Saga", issue: "54", year: "2018" }).map((rung) => rung.q),
      ["Saga 54", "Saga"],
    );
    assert.deepEqual(
      searchLadder({ kind: "magazine", title: "Linux Magazin", year: "2026" }).map((rung) => rung.q),
      ["Linux Magazin", "Linux Magazin 2026"],
    );
    assert.deepEqual(
      searchLadder({ kind: "music", artist: "Queen", album: "Jazz", year: "1978" }).map((rung) => rung.q),
      ["Jazz", "Queen Jazz"],
    );
  });

  it("round-trips search params in stable order", () => {
    const params = buildFindSearchParams({ q: "saga", kind: "comic", title: "Saga" });
    assert.equal(params.toString(), "q=saga&kind=comic&title=Saga");
    const fields = findFieldsFromSearchParams(params);
    assert.equal(fields.q, "saga");
    assert.equal(fields.kind, "comic");
    assert.equal(fields.title, "Saga");
    assert.equal(fields.author, "");
  });

  it("sends Hall gaps to Find with series and hole", () => {
    assert.deepEqual(gapFindFields({ series_name: "Saga", missing_index: "54", kind: "comic", gap: true }), {
      q: "Saga 54",
      kind: "comic",
      author: "",
      title: "",
      isbn: "",
      series: "Saga",
      issue: "54",
      artist: "",
      album: "",
      year: "",
    });
    assert.equal(
      findHref(gapFindFields({ series_name: "Saga", missing_index: "54", kind: "comic" })),
      "/search?q=Saga+54&kind=comic&series=Saga&issue=54",
    );
    assert.equal(
      findHref(
        gapFindFields({
          series_name: "Linux Magazin",
          series_index: "2026-09",
          kind: "magazine",
          year: 2026,
        }),
      ),
      "/search?q=Linux+Magazin+2026-09&kind=magazine&title=Linux+Magazin+2026-09&year=2026",
    );
  });

  it("deep-links owned multipart gaps with Part n/total chase shape", () => {
    const fields = gapFindFields({
      kind: "audiobook",
      gap_type: "multipart",
      author: "Feist",
      title: "Magician",
      missing_index: "2",
      part_set: { total: 5, owned: [3], style: "part", base: "Raymond E Feist Magician" },
    });
    assert.equal(fields.kind, "audiobook");
    assert.match(fields.q, /Part 2\/5/);
    assert.equal(fields.title, "Raymond E Feist Magician");
    assert.match(findHref(fields), /Part\+2%2F5|Part\+2\/5/);
  });

  it("prefills book series holes with author, year, and honest ISBN only", () => {
    assert.deepEqual(
      gapFindFields({
        kind: "book",
        series_name: "Dune",
        missing_index: "2",
        title: "Dune Messiah",
        author: "Frank Herbert",
        year: 1969,
        gap: true,
      }),
      {
        q: "Dune 2",
        kind: "book",
        author: "Frank Herbert",
        title: "Dune Messiah",
        isbn: "",
        series: "",
        issue: "",
        artist: "",
        album: "",
        year: "1969",
      },
    );
    assert.equal(
      findHref(
        gapFindFields({
          kind: "book",
          series_name: "Dune",
          missing_index: "2",
          title: "Dune Messiah",
          author: "Frank Herbert",
          year: 1969,
        }),
      ),
      "/search?q=Dune+2&kind=book&author=Frank+Herbert&title=Dune+Messiah&year=1969",
    );
  });

  it("prefills music holes with artist and album, never ISBN", () => {
    const fields = gapFindFields({
      kind: "music",
      series_name: "Kind of Blue",
      missing_index: "2",
      title: "Freddie Freeloader",
      author: "Miles",
      gap: true,
    });
    assert.equal(fields.kind, "music");
    assert.equal(fields.artist, "Miles");
    assert.equal(fields.album, "Kind of Blue");
    assert.equal(fields.isbn, "");
    assert.equal(findHref(fields), "/search?q=Kind+of+Blue+2&kind=music&artist=Miles&album=Kind+of+Blue");
  });

  it("builds a local search href with the same fields", () => {
    assert.equal(searchHref({ q: "dune", kind: "book" }), "/search?q=dune&kind=book");
    assert.equal(searchHref({}), "/search");
  });

  it("morphs visible Find fields by kind", () => {
    assert.deepEqual(visibleFindFields("book"), ["title", "author", "isbn", "year"]);
    assert.deepEqual(visibleFindFields("magazine"), ["title", "author", "isbn", "year"]);
    assert.deepEqual(visibleFindFields("comic"), ["series", "issue", "year"]);
    assert.deepEqual(visibleFindFields("music"), ["artist", "album", "year"]);
    assert.deepEqual(visibleFindFields("audiobook"), ["title", "author", "isbn"]);
    assert.deepEqual(visibleFindFields(""), []);
  });

  it("drops a stale ISBN when the kind becomes music", () => {
    const pruned = pruneFieldsForKind("music", {
      q: "Night at the Opera",
      kind: "book",
      title: "Dune",
      isbn: "9780441172719",
      author: "Herbert",
      artist: "Queen",
      album: "A Night at the Opera",
    });
    assert.equal(pruned.kind, "music");
    assert.equal(pruned.isbn, "");
    assert.equal(pruned.title, "");
    assert.equal(pruned.artist, "Queen");
    assert.equal(pruned.album, "A Night at the Opera");
  });

  it("sends fielded sought plus the selected hit on Request", () => {
    const body = requestBodyFromHit(
      {
        title: "VA-Guardians.Of.The.Galaxy.Awesome.Mix.Vol.1-202",
        guid: "g-mix",
        kind: "music",
        download_url: "https://example.test/mix.nzb",
        category: 3010,
        size: 99,
      },
      { kind: "music", artist: "Various Artists", album: "Awesome Mix Vol. 1", isbn: "9780441172719" },
    );
    assert.equal(body.title, "Awesome Mix Vol. 1");
    assert.equal(body.kind, "music");
    assert.equal(body.isbn, "");
    assert.equal(body.sought.album, "Awesome Mix Vol. 1");
    assert.equal(body.sought.isbn, "");
    assert.equal(body.selected.guid, "g-mix");
    assert.equal(body.selected.title, "VA-Guardians.Of.The.Galaxy.Awesome.Mix.Vol.1-202");
  });

  it("keeps the indexer host on the selected hit", () => {
    const body = requestBodyFromHit(
      {
        title: "Dune",
        guid: "g-dune",
        kind: "book",
        host_id: "extra1",
        host_name: "Books.nzb",
      },
      { kind: "book", title: "Dune" },
    );
    assert.equal(beyondHostName(body.selected), "Books.nzb");
    assert.equal(body.host_id, "extra1");
    assert.equal(body.selected.host_name, "Books.nzb");
  });
});


describe("catalog gap fan-out", () => {
  it("detects Hall gap queries and follows the ladder instead of the full prefill", () => {
    const comic = { kind: "comic", series: "Saga", issue: "54", q: "Saga 54" };
    assert.equal(isCatalogGapQuery(comic), true);
    assert.deepEqual(
      catalogGapFanoutQueries(comic, { cap: 5 }).map((row) => [row.q, row.series, row.issue]),
      [
        ["Saga 54", "Saga", "54"],
        ["Saga", "Saga", ""],
      ],
    );
    const book = gapFindFields({
      kind: "book",
      series_name: "Dune",
      missing_index: "2",
      title: "Dune Messiah",
      author: "Frank Herbert",
      year: 1969,
    });
    const queries = catalogGapFanoutQueries(book);
    assert.deepEqual(queries.map((row) => row.q), ["Dune Messiah", "Dune Messiah Frank Herbert"]);
    assert.ok(queries.every((row) => row.year === ""));
    assert.equal(queries[0].author, "");
  });

  it("ranks complete sets ahead of thin singles", () => {
    const ranked = rankBeyondByCompleteness([
      { found: 1, total: 5, complete: false },
      { found: 5, total: 5, complete: true },
      { found: 3, total: 5, complete: false },
    ]);
    assert.equal(ranked[0].complete, true);
    assert.equal(ranked[1].found, 3);
  });
});

describe("NYT bestsellers presets", () => {
  it("builds Find deep links for list and date", () => {
    assert.equal(bestsellersHref(), "/noted?preset=nyt&list=hardcover-fiction");
    assert.equal(
      bestsellersHref({ list: "hardcover-nonfiction", date: "2024-01-07" }),
      "/noted?preset=nyt&list=hardcover-nonfiction&date=2024-01-07",
    );
    assert.deepEqual(bestsellersFromSearchParams(new URLSearchParams("preset=nyt&list=hardcover-fiction")), {
      list: "hardcover-fiction",
      date: "current",
    });
    assert.equal(bestsellersFromSearchParams(new URLSearchParams("discover=7030")), null);
  });

  it("deep-links shelved hits to the work and misses to Search then Find", () => {
    assert.equal(nytHitHref({ shelved: { id: "w1" }, title: "Dune" }), "/works/w1");
    assert.equal(
      nytHitHref({ title: "Dune", author: "Frank Herbert", isbn: "9780441172719" }),
      "/search?q=Frank+Herbert+Dune&kind=book&author=Frank+Herbert&title=Dune&isbn=9780441172719",
    );
    assert.equal(
      nytHitFindHref({ title: "Dune", author: "Frank Herbert", isbn: "9780441172719" }),
      "/search?q=Frank+Herbert+Dune&kind=book&author=Frank+Herbert&title=Dune&isbn=9780441172719",
    );
  });
});
