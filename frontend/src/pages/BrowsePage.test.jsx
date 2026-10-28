// @vitest-environment jsdom
import assert from "node:assert/strict";
import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, it } from "vitest";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import BrowsePage from "./BrowsePage.jsx";

const realFetch = globalThis.fetch;

const book = {
  id: "86f007ee",
  kind: "book",
  title: "The 1619 Project",
  author: "Nikole Hannah-Jones",
};

const wanted = {
  ...book,
  id: "wanted-audio",
  title: "Circe",
  author: "Madeline Miller",
  audiobook: {
    applicable: true,
    shelved: null,
    find: { kind: "audiobook", title: "Circe", author: "Madeline Miller" },
  },
};

function json(data) {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

function renderBrowse() {
  return render(
    <MemoryRouter initialEntries={["/browse"]}>
      <Routes>
        <Route element={<Outlet context={{ user: { role: "reader", display_name: "Ada" } }} />}>
          <Route path="browse" element={<BrowsePage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
}

describe("BrowsePage Stacks cards", () => {
  beforeEach(() => {
    window.matchMedia = (query) => ({
      matches: false,
      media: query,
      addEventListener() {},
      removeEventListener() {},
      addListener() {},
      removeListener() {},
      dispatchEvent() {
        return false;
      },
    });
    globalThis.localStorage?.removeItem?.("librarian.browse.view");
    globalThis.fetch = async (input) => {
      const url = String(input);
      if (url.includes("/browse/facets")) return json({ authors: [], series: [], genres: [] });
      if (url.includes("/shelves")) return json({ shelves: [], presence: "" });
      if (url.includes("/browse")) return json({ items: [book, wanted], total: 2 });
      return json({});
    };
  });

  afterEach(() => {
    globalThis.fetch = realFetch;
  });

  it("shows title and author under each cover, and keeps the wanted note from replacing them", async () => {
    renderBrowse();
    const footers = await screen.findAllByTestId("stacks-card-footer");
    assert.equal(footers.length, 2);
    const projectCard = footers.find((node) => node.textContent.includes("The 1619 Project"));
    const circeCard = footers.find((node) => node.textContent.includes("Circe"));
    assert.ok(projectCard);
    assert.ok(circeCard);
    assert.ok(within(projectCard).getByText("Nikole Hannah-Jones"));
    assert.ok(within(circeCard).getByText("Madeline Miller"));
    assert.equal(circeCard.textContent.includes("The audiobook is wanted"), false);
    assert.ok(screen.getByText("The audiobook is wanted"));

    assert.equal(screen.queryByText("On the shelf"), null);
    assert.equal(screen.queryByRole("link", { name: "Read" }), null);
    assert.equal(screen.queryByRole("link", { name: "Download" }), null);
  });
});
