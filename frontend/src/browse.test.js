import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { BROWSE_LETTERS, browseFiltersFromSearchParams, browseHref } from "./browse.js";
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

describe("browse href helpers", () => {
  it("builds stacks URLs for author kind series favorites", () => {
    assert.equal(browseHref(), "/browse");
    assert.equal(browseHref({ kind: "book" }), "/browse?kind=book");
    assert.equal(browseHref({ author: "Stephen King" }), "/browse?author=Stephen+King");
    assert.equal(browseHref({ letter: "s" }), "/browse?letter=S");
    assert.equal(browseHref({ series: "Dune" }), "/browse?series=Dune");
    assert.equal(browseHref({ shelf: "favorites" }), "/browse?shelf=favorites");
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
});
