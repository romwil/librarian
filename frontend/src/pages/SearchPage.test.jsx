// @vitest-environment jsdom
import assert from "node:assert/strict";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, describe, it } from "vitest";
import SearchPage from "./SearchPage.jsx";

const realFetch = globalThis.fetch;
let calls;

function searchCalls() {
  return calls.filter((url) => url.includes("/api/search") && !url.includes("/api/search/beyond") && !url.includes("/api/search/ask"));
}

function beyondCalls() {
  return calls.filter((url) => url.includes("/api/search/beyond"));
}

function discoverCalls() {
  return calls.filter((url) => url.includes("/api/discover"));
}

function discoverUrl(index = 0) {
  return new URL(discoverCalls()[index], "http://localhost");
}

beforeEach(() => {
  calls = [];
  globalThis.fetch = async (url) => {
    const path = String(url);
    calls.push(path);
    if (path.includes("/api/discover")) {
      const query = new URL(path, "http://localhost").searchParams;
      const offset = Number(query.get("offset") || 0);
      const count = offset === 0 ? 12 : 4;
      const items = Array.from({ length: count }, (_, i) => ({
        guid: `g-${offset + i}`,
        title: `Ebook ${offset + i}`,
        kind: "book",
        category: "7020",
      }));
      return new Response(JSON.stringify({ items, categories: [], limit: 12, offset }), {
        status: 200,
        headers: { "content-type": "application/json" },
      });
    }
    return new Response(JSON.stringify({ local: [], beyond: [], public_domain: [] }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };
});

afterEach(() => {
  globalThis.fetch = realFetch;
});

function renderSearch(path = "/search") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<Outlet context={{ user: { role: "owner" }, features: {} }} />}>
          <Route path="/search" element={<SearchPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("Search prefill", () => {
  it("sends one precise query for a prefilled book, not every field ANDed together", async () => {
    renderSearch("/search?kind=book&title=Dune&author=Frank+Herbert&isbn=9780441172719&year=1965");
    await waitFor(() => assert.ok(searchCalls().length));
    const url = new URL(searchCalls()[0], "http://localhost");
    assert.equal(url.searchParams.get("beyond"), null);
    assert.equal(url.searchParams.get("q"), "Dune");
    assert.equal(url.searchParams.get("title"), "Dune");
    assert.equal(url.searchParams.get("author"), "Frank Herbert");
    assert.equal(url.searchParams.get("isbn"), "9780441172719");
    assert.ok(screen.getByDisplayValue("Frank Herbert"));
    assert.ok(screen.getByDisplayValue("9780441172719"));
  });

  it("keeps what the person typed as the query", async () => {
    renderSearch("/search?q=dune+herbert&kind=book&title=Dune&author=Frank+Herbert");
    await waitFor(() => assert.ok(searchCalls().length));
    const url = new URL(searchCalls()[0], "http://localhost");
    assert.equal(url.searchParams.get("q"), "dune herbert");
  });
});

describe("Search Discover", () => {
  it("stays collapsed and does not call discover until Discover is expanded", async () => {
    renderSearch("/search?kind=audiobook");
    const door = screen.getByRole("link", { name: "New & noted" });
    assert.equal(door.getAttribute("href"), "/noted");
    assert.equal(screen.queryByRole("link", { name: "Trending books" }), null);
    assert.equal(screen.queryByTestId("discover-cats"), null);
    assert.equal(screen.queryByRole("button", { name: "Magazines" }), null);
    assert.equal(screen.queryByRole("button", { name: "MP3" }), null);
    const toggle = screen.getByRole("button", { name: "Discover" });
    assert.equal(toggle.getAttribute("aria-expanded"), "false");
    assert.equal(toggle.parentElement?.className, "discover-launch");
    assert.equal(discoverCalls().length, 0);

    await userEvent.click(toggle);
    await screen.findByRole("button", { name: /^Ebook 0/ });
    assert.equal(discoverCalls().length, 1);
    const first = discoverUrl(0);
    assert.equal(first.pathname, "/api/discover");
    assert.equal(first.searchParams.get("cat"), "7020");
    assert.equal(first.searchParams.get("limit"), "12");
    assert.equal(first.searchParams.get("kind"), null);
    assert.equal(first.searchParams.get("offset"), null);
    assert.equal(screen.getByRole("button", { name: "Discover" }).getAttribute("aria-expanded"), "true");
    assert.equal(screen.getByRole("button", { name: "Previous" }).disabled, true);

    await userEvent.click(screen.getByRole("button", { name: "Book" }));
    assert.equal(discoverCalls().length, 1);

    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await screen.findByRole("button", { name: /^Ebook 12/ });
    assert.equal(discoverCalls().length, 2);
    const second = discoverUrl(1);
    assert.equal(second.searchParams.get("cat"), "7020");
    assert.equal(second.searchParams.get("limit"), "12");
    assert.equal(second.searchParams.get("offset"), "12");
    assert.equal(second.searchParams.get("kind"), null);
    assert.equal(screen.getByRole("button", { name: "Next" }).disabled, true);

    await userEvent.click(screen.getByRole("button", { name: "Previous" }));
    await screen.findByRole("button", { name: /^Ebook 0/ });
    assert.equal(discoverCalls().length, 3);
    assert.equal(discoverUrl(2).searchParams.get("cat"), "7020");
    assert.equal(discoverUrl(2).searchParams.get("limit"), "12");
    assert.equal(discoverUrl(2).searchParams.get("offset"), null);
  });

  it("does not call discover for a search until the fold is opened", async () => {
    renderSearch("/search?q=dune");
    await waitFor(() => assert.ok(searchCalls().length));
    assert.equal(discoverCalls().length, 0);
    await userEvent.click(screen.getByText("Discover"));
    await screen.findByRole("button", { name: /^Ebook 0/ });
    assert.equal(discoverCalls().length, 1);
    assert.equal(discoverUrl(0).searchParams.get("cat"), "7020");
    assert.equal(discoverUrl(0).searchParams.get("limit"), "12");
    assert.equal(discoverUrl(0).searchParams.get("kind"), null);
  });
});

function renderRole(role, path = "/search?q=dune") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<Outlet context={{ user: { role }, features: {} }} />}>
          <Route path="/search" element={<SearchPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("Search lanes", () => {
  it("owner auto-beyonds after local, without beyond=1 on the shelf call", async () => {
    renderSearch("/search?q=dune");
    await waitFor(() => assert.ok(searchCalls().length));
    await waitFor(() => assert.ok(beyondCalls().length));
    assert.equal(new URL(searchCalls()[0], "http://localhost").searchParams.get("beyond"), null);
    assert.match(beyondCalls()[0], /\/api\/search\/beyond/);
  });

  it("reader submit never hits beyond and offers Ask the house", async () => {
    renderRole("reader");
    await waitFor(() => assert.ok(searchCalls().length));
    assert.ok(await screen.findByRole("button", { name: "Ask the house" }));
    assert.equal(beyondCalls().length, 0);
    assert.equal(screen.queryByRole("heading", { name: "Beyond the shelves" }), null);
    assert.equal(screen.queryByText(/NZBFinder/i), null);
    assert.equal(screen.queryByRole("button", { name: "Discover" }), null);
  });

  it("keeps local covers visible while beyond is still looking", async () => {
    let releaseBeyond;
    const pending = new Promise((resolve) => {
      releaseBeyond = resolve;
    });
    globalThis.fetch = async (url) => {
      const path = String(url);
      calls.push(path);
      if (path.includes("/api/search/beyond")) {
        await pending;
        return new Response(JSON.stringify({ beyond: [{ title: "Dune NZB", guid: "g-dune", kind: "book" }] }), {
          status: 200,
          headers: { "content-type": "application/json" },
        });
      }
      return new Response(
        JSON.stringify({
          local: [{ id: "w1", title: "Dune on the shelf", kind: "book", author: "Herbert" }],
          beyond: [],
          public_domain: [],
        }),
        { status: 200, headers: { "content-type": "application/json" } },
      );
    };
    renderSearch("/search?q=dune");
    const localCovers = await screen.findAllByRole("button", { name: /Dune on the shelf/ });
    assert.ok(localCovers.length);
    assert.equal(beyondCalls().length, 1);
    assert.equal(screen.queryByText("Dune NZB"), null);
    releaseBeyond();
    assert.ok((await screen.findAllByRole("button", { name: /Dune NZB/ })).length);
  });
});
