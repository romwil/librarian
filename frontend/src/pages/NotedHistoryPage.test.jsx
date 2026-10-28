// @vitest-environment jsdom
import assert from "node:assert/strict";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes } from "react-router-dom";
import { afterEach, it } from "vitest";
import NotedHistoryPage from "./NotedHistoryPage.jsx";

const realFetch = globalThis.fetch;

afterEach(() => {
  globalThis.fetch = realFetch;
});

it("labels a history range as the household model", async () => {
  globalThis.fetch = async () => new Response(
    JSON.stringify({
      items: [
        {
          title: "Model Book",
          author: "A. Writer",
          isbn13: "9780441172719",
          work_id: "work-model",
          weeks: ["2026-10-18"],
          status: "matched",
        },
      ],
      origin_label: "These titles came from the household model, not the New York Times API.",
    }),
    { headers: { "content-type": "application/json" } },
  );

  render(
    <MemoryRouter>
      <Routes>
        <Route element={<Outlet context={{ user: { role: "owner" } }} />}>
          <Route path="/" element={<NotedHistoryPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );

  await userEvent.click(screen.getByRole("button", { name: "Load range" }));
  await screen.findByText("Model Book");
  const origin = await screen.findByTestId("noted-history-origin");
  assert.match(origin.textContent, /household model/i);
  assert.match(origin.textContent, /not the New York Times API/i);
  assert.equal(screen.getAllByTestId("noted-book").length, 1);
  assert.equal(screen.getByTestId("noted-book").getAttribute("data-status"), "matched");
  assert.equal(screen.queryByText(/Weeks:/), null);
  assert.equal(document.body.textContent.includes("2026-10-18"), false);
  assert.equal(screen.getByRole("link", { name: "Open" }).getAttribute("href"), "/works/work-model");
  assert.equal(screen.queryByRole("button", { name: "Add to Wanted" }), null);
});

it("shows Thinking before a deferred range returns and aligns the form row", async () => {
  let release;
  const gate = new Promise((resolve) => {
    release = resolve;
  });
  globalThis.fetch = () =>
    gate.then(
      () =>
        new Response(
          JSON.stringify({
            items: [
              {
                title: "Late Book",
                author: "A. Writer",
                isbn13: "9780000000001",
                weeks: ["2026-10-18"],
                status: "missing",
              },
            ],
          }),
          { headers: { "content-type": "application/json" } },
        ),
    );

  render(
    <MemoryRouter>
      <Routes>
        <Route element={<Outlet context={{ user: { role: "owner" } }} />}>
          <Route path="/" element={<NotedHistoryPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );

  const load = screen.getByRole("button", { name: "Load range" });
  assert.equal(load.parentElement.className, "cta-row align-end");
  await userEvent.click(load);
  const marks = await screen.findAllByText("Thinking…");
  assert.ok(marks.length >= 1);
  assert.equal(screen.queryByText("Late Book"), null);
  assert.ok(screen.getByLabelText("Start date"));
  assert.equal(load.getAttribute("aria-busy"), "true");
  assert.equal(load.disabled, true);
  release();
  await screen.findByText("Late Book");
  assert.equal(screen.queryByText("Thinking…"), null);
  assert.equal(screen.queryByText(/Weeks:/), null);
  assert.ok(screen.getByRole("button", { name: "Add to Wanted" }));
});

it("collapses duplicate titles and keeps one action on the book", async () => {
  const posts = [];
  const weeks = ["2026-08-30", "2026-09-06", "2026-09-13", "2026-09-20", "2026-09-27", "2026-10-04"];
  globalThis.fetch = async (_url, options = {}) => {
    if (options.method === "POST") {
      posts.push(JSON.parse(options.body));
      return new Response(JSON.stringify({ added: 1 }), { headers: { "content-type": "application/json" } });
    }
    return new Response(
      JSON.stringify({
        items: [
          {
            title: "The Correspondent",
            author: "Virginia Evans",
            isbn13: "9780593440955",
            weeks,
            status: "missing",
          },
          {
            title: "The Correspondent",
            author: "Virginia Evans",
            isbn13: "9780593440962",
            weeks,
            status: "missing",
          },
          {
            title: " the correspondent ",
            author: "Virginia Evans",
            weeks: ["2026-08-30"],
            status: "missing",
          },
          {
            title: "Culpability",
            author: "Bruce Holsinger",
            isbn13: "9780593876543",
            weeks: ["2026-10-04", "2026-10-11"],
            status: "wanted",
            wanted: true,
          },
          {
            title: "Buckeye",
            author: "Patrick Ryan",
            isbn13: "9780593594841",
            work_id: "work-buckeye",
            weeks: ["2026-10-04"],
            status: "matched",
            shelved: true,
          },
        ],
      }),
      { headers: { "content-type": "application/json" } },
    );
  };

  render(
    <MemoryRouter>
      <Routes>
        <Route element={<Outlet context={{ user: { role: "owner" } }} />}>
          <Route path="/" element={<NotedHistoryPage />} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );

  await userEvent.click(screen.getByRole("button", { name: "Load range" }));
  await screen.findByText("The Correspondent");
  const cards = screen.getAllByTestId("noted-book");
  assert.equal(cards.length, 3);
  assert.equal(screen.getAllByText("The Correspondent").length, 1);
  assert.equal(document.body.textContent.includes("2026-08-30"), false);
  assert.equal(document.body.textContent.includes("2026-10-11"), false);
  assert.equal(screen.queryByText(/Weeks:/), null);
  assert.match(document.body.textContent, /6 weeks/);
  assert.match(document.body.textContent, /2 weeks/);
  assert.equal(document.body.textContent.includes("1 week"), false);
  assert.ok(screen.getByRole("button", { name: "Add missing" }));
  assert.equal(screen.getAllByRole("button", { name: "Add to Wanted" }).length, 1);
  const wanted = cards.find((card) => card.getAttribute("data-status") === "wanted");
  assert.ok(wanted);
  assert.equal(wanted.textContent.includes("Add to Wanted"), false);
  assert.equal(screen.getByRole("link", { name: "Open" }).getAttribute("href"), "/works/work-buckeye");

  await userEvent.click(screen.getByRole("button", { name: "Add to Wanted" }));
  assert.equal(posts.length, 1);
  assert.equal(posts[0].items.length, 1);
  assert.equal(posts[0].items[0].title, "The Correspondent");
  assert.equal(JSON.stringify(posts[0]).includes("2026-08-30"), false);
  assert.equal(screen.queryByRole("button", { name: "Add to Wanted" }), null);
});
