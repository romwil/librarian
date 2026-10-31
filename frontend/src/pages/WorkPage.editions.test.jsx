// @vitest-environment jsdom
import assert from "node:assert/strict";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Outlet, Route, Routes, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, it } from "vitest";
import WorkPage from "./WorkPage.jsx";

const realFetch = globalThis.fetch;
const media = HTMLMediaElement.prototype;
const realMedia = { play: media.play, pause: media.pause, load: media.load };

const ABS_HREF = "http://10.10.1.202:13378/item/already-linked";

const BOOK = {
  work: {
    id: "1619",
    title: "The 1619 Project",
    author: "Nikole Hannah-Jones",
    kind: "book",
    review_state: "",
  },
  can_download: true,
  can_read: true,
  files: [
    { id: "pdf", filename: "1619.pdf", reading_room: true },
    { id: "epub", filename: "1619.epub", reading_room: true },
  ],
  file_count: 2,
  favorite: false,
  listen: { can_listen: false },
  authors: [{ id: "a-nhj", display_name: "Nikole Hannah-Jones", sort_name: "Hannah-Jones, Nikole" }],
  editions: [
    { id: "ed-hard", kind: "book", isbn13: "9780593230572", asin: null, format: "Hardcover" },
    { id: "ed-audio", kind: "audiobook", isbn13: null, asin: "B09LISTEN", format: "Audiobook" },
  ],
  related: [],
  whispers: [],
};

const AUDIO = {
  work: { id: "audio-1", title: "Long Listen", author: "N. Arrator", kind: "audiobook", review_state: "" },
  can_download: true,
  can_read: false,
  files: [
    { id: "mp3", filename: "01.mp3" },
    { id: "m4b", filename: "book.m4b" },
  ],
  file_count: 2,
  favorite: false,
  listen: { can_listen: true },
  editions: [{ id: "ed-audio", kind: "audiobook", isbn13: null, asin: "B09LISTEN", format: "Audiobook" }],
  related: [],
  whispers: [],
};

const LINKED = {
  ...AUDIO,
  work: { ...AUDIO.work, id: "linked-1" },
  listen: {
    can_listen: true,
    player: { href: ABS_HREF, label: "Open in player", provider: "audiobookshelf" },
  },
};

function Where() {
  const location = useLocation();
  return <output data-testid="where">{`${location.pathname}${location.search}`}</output>;
}

const MISSING_AUDIO = {
  ...BOOK,
  work: { ...BOOK.work, id: "miss-audio", narrator: "January LaVoy" },
  audiobook: {
    applicable: true,
    shelved: null,
    narrator: "January LaVoy",
    find: { kind: "audiobook", title: "The 1619 Project", author: "Nikole Hannah-Jones" },
  },
  wanted: null,
};

function renderWork(path, role = "reader") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route element={<Outlet context={{ user: { role, display_name: "Ada" } }} />}>
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
  globalThis.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  };
  globalThis.fetch = async (url) => {
    const path = String(url);
    let body = {};
    if (path.endsWith("/api/works/1619")) body = BOOK;
    else if (path.endsWith("/api/works/miss-audio")) body = MISSING_AUDIO;
    else if (path.endsWith("/api/works/audio-1")) body = AUDIO;
    else if (path.endsWith("/api/works/linked-1")) body = LINKED;
    else if (path.includes("/chapters")) body = { chapters: [] };
    return new Response(JSON.stringify(body), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };
});

afterEach(() => {
  Object.assign(media, realMedia);
  globalThis.fetch = realFetch;
});

describe("Work page editions and listen", () => {
  it("lists edition isbn13, asin, and format", async () => {
    renderWork("/works/1619");
    const section = await screen.findByRole("region", { name: "Editions and formats" });
    const items = within(section).getAllByRole("listitem").map((node) => node.textContent);
    assert.equal(items.length, 2);
    assert.match(items[0], /Hardcover/);
    assert.match(items[0], /9780593230572/);
    assert.match(items[1], /Audiobook/);
    assert.match(items[1], /B09LISTEN/);
    assert.equal(screen.getByTestId("work-authors").textContent.trim(), "Nikole Hannah-Jones");
  });

  it("keeps a missing audiobook on the work page", async () => {
    renderWork("/works/miss-audio", "owner");
    const section = await screen.findByRole("region", { name: "Editions and formats" });
    assert.match(section.textContent, /Audiobook/);
    assert.match(section.textContent, /B09LISTEN/);
    await userEvent.click(screen.getByText("Series, catalog, and notes"));
    assert.ok(screen.getByText("The audiobook is wanted"));
    assert.ok(screen.getByRole("button", { name: "Add to Wanted" }));
    assert.ok(screen.getByRole("link", { name: "Find beyond" }));
  });

  it("opens Listen on the m4b and does not invent an Audiobookshelf link", async () => {
    renderWork("/works/audio-1");
    const section = await screen.findByRole("region", { name: "Editions and formats" });
    assert.match(section.textContent, /B09LISTEN/);
    const listen = await screen.findByTestId("work-listen");
    assert.equal(listen.tagName, "BUTTON");
    assert.equal(screen.queryByRole("link", { name: "Listen" }), null);
    await userEvent.click(listen);
    assert.equal(screen.getByTestId("where").textContent, "/works/audio-1?listen=1&file=m4b");
    assert.equal(
      screen
        .queryAllByRole("link")
        .some((node) => String(node.getAttribute("href") || "").includes("audiobookshelf")),
      false,
    );
  });

  it("opens Audiobookshelf only when a link is already on the work", async () => {
    renderWork("/works/linked-1");
    const listen = await screen.findByTestId("work-listen");
    assert.equal(listen.tagName, "A");
    assert.equal(listen.getAttribute("href"), ABS_HREF);
    assert.equal(screen.getByTestId("where").textContent, "/works/linked-1");
  });
});
