// @vitest-environment jsdom
import assert from "node:assert/strict";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, it } from "vitest";
import WorkPage from "./pages/WorkPage.jsx";

const media = HTMLMediaElement.prototype;
const real = { play: media.play, pause: media.pause, load: media.load };
const realFetch = globalThis.fetch;

const AUDIOBOOK = {
  work: { id: "ab-1", title: "Long Listen", author: "N. Arrator", kind: "audiobook", review_state: "" },
  can_download: true,
  can_read: false,
  files: [
    { id: "p1", filename: "Part 1.m4b" },
    { id: "p2", filename: "Part 2.m4b" },
  ],
  file_count: 2,
  favorite: false,
  listen: { can_listen: true },
  related: [],
  whispers: [],
};

function Where() {
  const location = useLocation();
  return <output data-testid="where">{`${location.pathname}${location.search}`}</output>;
}

function renderWork(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<Outlet context={{ user: { role: "reader", display_name: "Kid" } }} />}>
          <Route path="/works/:id" element={<WorkPage />} />
        </Route>
      </Routes>
      <Where />
    </MemoryRouter>,
  );
}

beforeEach(() => {
  media.play = () => Promise.resolve();
  media.pause = () => {};
  media.load = () => {};
  globalThis.fetch = async (url) => {
    const path = String(url);
    let body = {};
    if (path.endsWith("/api/works/ab-1")) body = AUDIOBOOK;
    else if (path.includes("/chapters")) body = { chapters: [] };
    return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
  };
});

afterEach(() => {
  Object.assign(media, real);
  globalThis.fetch = realFetch;
});

describe("Work page listen shell", () => {
  it("opens the Listening room from Listen and writes the shareable deep link", async () => {
    renderWork("/works/ab-1");
    await userEvent.click(await screen.findByTestId("work-listen"));
    assert.ok(await screen.findByRole("dialog", { name: "Long Listen" }));
    assert.equal(screen.getByTestId("where").textContent, "/works/ab-1?listen=1");

    await userEvent.click(screen.getByRole("button", { name: "Close" }));
    await waitFor(() => assert.equal(screen.queryByRole("dialog"), null));
    assert.equal(screen.getByTestId("where").textContent, "/works/ab-1");
  });

  it("honours ?listen=1&file= on arrival and starts on that part", async () => {
    renderWork("/works/ab-1?listen=1&file=p2");
    assert.ok(await screen.findByRole("dialog", { name: "Long Listen" }));
    assert.match(screen.getByTestId("listen-audio").getAttribute("src"), /file=p2$/);
  });

  it("ignores ?listen=1 on a work that cannot be heard in the app", async () => {
    AUDIOBOOK.can_download = false;
    try {
      renderWork("/works/ab-1?listen=1");
      assert.ok(await screen.findByRole("heading", { name: "Long Listen" }));
      assert.equal(screen.queryByRole("dialog"), null);
    } finally {
      AUDIOBOOK.can_download = true;
    }
  });
});
