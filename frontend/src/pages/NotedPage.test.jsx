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
