import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  buildFindSearchParams,
  composeSearchQuery,
  findFieldsFromSearchParams,
  findHref,
  gapFindFields,
  pruneFieldsForKind,
  requestBodyFromHit,
  searchHref,
  shouldShowDiscover,
  findKindOptions,
  visibleFindFields,
  beyondHostName,
} from "./find.js";

describe("Find query builder", () => {
  it("builds /find with q and kind", () => {
    assert.equal(findHref({ q: "dune", kind: "book" }), "/find?q=dune&kind=book");
  });

  it("adds advanced author, title, and isbn when used", () => {
    assert.equal(
      findHref({ q: "dune", kind: "book", author: "Herbert", title: "Dune", isbn: "9780441172719" }),
      "/find?q=dune&kind=book&author=Herbert&title=Dune&isbn=9780441172719",
    );
  });

  it("leaves /find empty when there is no query", () => {
    assert.equal(findHref({}), "/find");
    assert.equal(findHref({ q: "  ", kind: "" }), "/find");
  });

  it("shows Discover when Find has no query", () => {
    assert.equal(shouldShowDiscover({}), true);
    assert.equal(shouldShowDiscover({ q: "dune" }), false);
    assert.equal(shouldShowDiscover({ kind: "comic" }), true);
    assert.equal(findKindOptions(false).some(([value]) => value === "movie"), false);
    assert.equal(findKindOptions(true).some(([value]) => value === "movie"), true);
  });

  it("composes a beyond query from split fields", () => {
    assert.equal(composeSearchQuery({ q: "dune", author: "Herbert" }), "dune Herbert");
    assert.equal(composeSearchQuery({ author: "King", isbn: "9781501142970" }), "King 9781501142970");
    assert.equal(composeSearchQuery({ artist: "Queen", album: "News of the World", year: "1977" }), "Queen News of the World 1977");
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
      "/find?q=Saga+54&kind=comic&series=Saga&issue=54",
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
      "/find?q=Linux+Magazin+2026-09&kind=magazine&title=Linux+Magazin+2026-09&year=2026",
    );
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
      "/find?q=Dune+2&kind=book&author=Frank+Herbert&title=Dune+Messiah&year=1969",
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
    assert.equal(findHref(fields), "/find?q=Kind+of+Blue+2&kind=music&artist=Miles&album=Kind+of+Blue");
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
    assert.deepEqual(visibleFindFields("audiobook"), ["title", "author"]);
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
