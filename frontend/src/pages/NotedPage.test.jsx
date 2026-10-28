// @vitest-environment jsdom
import assert from "node:assert/strict";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import NotedPage from "./NotedPage.jsx";

const realFetch = globalThis.fetch;
let calls = 0;

beforeEach(() => {
  calls = 0;
  globalThis.fetch = async () => {
    calls += 1;
    return new Response(
      JSON.stringify({
        can_add: true,
        lists: [
          { id: "open-library-daily", label: "Open Library daily" },
          { id: "open-library-weekly", label: "Open Library weekly" },
        ],
        lanes: [
          { id: "open-library-daily", label: "Open Library daily", items: [{ title: "Daily book", kind: "book", wanted: { kinds: [] } }] },
          { id: "open-library-weekly", label: "Open Library weekly", items: [{ title: "Weekly book", kind: "book", wanted: { kinds: [] } }] },
        ],
      }),
      { headers: { "content-type": "application/json" } },
    );
  };
});

afterEach(() => {
  globalThis.fetch = realFetch;
});

it("switches cached New & noted lists without another request", async () => {
  render(<MemoryRouter><NotedPage /></MemoryRouter>);
  await screen.findByText("Daily book");
  await userEvent.click(screen.getByRole("button", { name: "Open Library weekly" }));
  await screen.findByText("Weekly book");
  assert.equal(calls, 1);
});

it("opens the cached NYT chip selected by Maintain", async () => {
  globalThis.fetch = async () => new Response(
    JSON.stringify({
      can_add: true,
      lists: [
        { id: "open-library-daily", label: "Open Library daily" },
        { id: "nyt-hardcover-fiction", label: "Hardcover Fiction" },
      ],
      lanes: [
        { id: "open-library-daily", label: "Open Library daily", items: [{ title: "Daily book", kind: "book", wanted: { kinds: [] } }] },
        { id: "nyt-hardcover-fiction", label: "Hardcover Fiction", items: [{ title: "NYT book", kind: "book", wanted: { kinds: [] } }] },
      ],
    }),
    { headers: { "content-type": "application/json" } },
  );

  render(<MemoryRouter initialEntries={["/noted?preset=nyt&list=hardcover-fiction"]}><NotedPage /></MemoryRouter>);
  await screen.findByText("NYT book");
  assert.equal(screen.getByRole("button", { name: "Hardcover Fiction" }).getAttribute("aria-pressed"), "true");
});

it("says a filled New York Times chip came from the household model", async () => {
  globalThis.fetch = async () => new Response(
    JSON.stringify({
      can_add: false,
      lists: [{ id: "nyt-hardcover-fiction", label: "Hardcover Fiction" }],
      lanes: [{
        id: "nyt-hardcover-fiction",
        label: "Hardcover Fiction",
        origin_label: "These titles came from the household model, not the New York Times API.",
        items: [{ title: "Model Book", author: "A. Writer", kind: "book", source: "household" }],
      }],
    }),
    { headers: { "content-type": "application/json" } },
  );

  render(<MemoryRouter initialEntries={["/noted?preset=nyt&list=hardcover-fiction"]}><NotedPage /></MemoryRouter>);
  await screen.findByText("Model Book");
  const origin = await screen.findByTestId("noted-origin");
  assert.match(origin.textContent, /household model/i);
  assert.match(origin.textContent, /not the New York Times API/i);
});

it("shows one card when the same title is listed twice", async () => {
  globalThis.fetch = async () => new Response(
    JSON.stringify({
      can_add: true,
      lists: [{ id: "nyt-hardcover-fiction", label: "Hardcover Fiction" }],
      lanes: [{
        id: "nyt-hardcover-fiction",
        label: "Hardcover Fiction",
        items: [
          {
            title: "The Correspondent",
            author: "Virginia Evans",
            isbn: "9780593440955",
            kind: "book",
            weeks: ["2026-08-30", "2026-09-06", "2026-09-13"],
            wanted: { kinds: ["book"] },
          },
          {
            title: "The Correspondent",
            author: "Virginia Evans",
            isbn: "9780593440962",
            kind: "book",
            weeks: ["2026-08-30", "2026-09-06", "2026-09-13", "2026-09-20", "2026-09-27", "2026-10-04"],
            wanted: { kinds: ["book"] },
          },
          {
            title: "Buckeye",
            author: "Patrick Ryan",
            kind: "book",
            shelved: { id: "work-buckeye" },
            wanted: { kinds: [] },
          },
        ],
      }],
    }),
    { headers: { "content-type": "application/json" } },
  );

  render(<MemoryRouter initialEntries={["/noted?preset=nyt&list=hardcover-fiction"]}><NotedPage /></MemoryRouter>);
  await screen.findByText("The Correspondent");
  assert.equal(screen.getAllByTestId("noted-item").length, 2);
  assert.equal(screen.getAllByText("The Correspondent").length, 1);
  assert.equal(document.body.textContent.includes("2026-08-30"), false);
  assert.equal(document.body.textContent.includes("2026-10-04"), false);
  assert.match(document.body.textContent, /6 weeks/);
  assert.equal(screen.getAllByRole("button", { name: "Add to Wanted" }).length, 1);
  assert.equal(screen.getByRole("link", { name: "On the shelf" }).getAttribute("href"), "/works/work-buckeye");
  assert.equal(screen.queryByText(/audiobook/i), null);
});
