// @vitest-environment jsdom
import assert from "node:assert/strict";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import CoverCard from "./CoverCard.jsx";
import { WorkPeekProvider } from "./WorkPeekProvider.jsx";

const realFetch = globalThis.fetch;

const book = {
  id: "book-1",
  kind: "book",
  title: "The 1619 Project",
  author: "Nikole Hannah-Jones",
};

const wantedAudio = {
  applicable: true,
  shelved: null,
  find: { kind: "audiobook", title: "The 1619 Project", author: "Nikole Hannah-Jones" },
};

function json(data) {
  return new Response(JSON.stringify(data), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

function renderCard(work, props = {}) {
  return render(
    <MemoryRouter>
      <WorkPeekProvider>
        {/* household `role`, not ARIA */}
        {/* eslint-disable-next-line jsx-a11y/aria-role */}
        <CoverCard work={work} role="reader" {...props} />
      </WorkPeekProvider>
    </MemoryRouter>,
  );
}

describe("CoverCard footer", () => {
  beforeEach(() => {
    globalThis.fetch = async (input) => {
      const url = String(input);
      if (url.includes("/auth/me")) return json({ user: { role: "reader" } });
      if (url.includes("/works/")) {
        return json({
          work: book,
          can_read: true,
          can_download: true,
          files: [{ id: "f1", filename: "1619.epub", on_disk: true }],
        });
      }
      return json({});
    };
  });

  afterEach(() => {
    globalThis.fetch = realFetch;
  });

  it("shows the title and author on a Stacks card, without On the shelf, Read, or Download", () => {
    renderCard(book, { cardMode: "stacks" });
    const footer = screen.getByTestId("stacks-card-footer");
    assert.ok(within(footer).getByText("The 1619 Project"));
    assert.ok(within(footer).getByText("Nikole Hannah-Jones"));
    assert.equal(within(footer).queryByText("On the shelf"), null);
    assert.equal(screen.queryByText("On the shelf"), null);
    assert.equal(screen.queryByRole("link", { name: "Read" }), null);
    assert.equal(screen.queryByRole("link", { name: "Download" }), null);
  });

  it("does not show a missing-audiobook line under the title and author", () => {
    renderCard({ ...book, audiobook: wantedAudio }, { cardMode: "stacks", role: "owner" });
    const footer = screen.getByTestId("stacks-card-footer");
    assert.ok(within(footer).getByText("The 1619 Project"));
    assert.ok(within(footer).getByText("Nikole Hannah-Jones"));
    assert.equal(screen.queryByText("The audiobook is wanted"), null);
    assert.equal(screen.queryByText("Wanted"), null);
    assert.equal(screen.queryByRole("button", { name: "Add to Wanted" }), null);
    assert.equal(screen.queryByRole("link", { name: "Search the shelves" }), null);
    assert.equal(screen.queryByText("On the shelf"), null);
    assert.equal(screen.queryByRole("link", { name: "Read" }), null);
    assert.equal(screen.queryByRole("link", { name: "Download" }), null);
  });

  it("keeps On the shelf and Read on a list card, without the missing audiobook", () => {
    renderCard({ ...book, audiobook: wantedAudio }, { role: "owner" });
    assert.ok(screen.getByText("On the shelf"));
    assert.ok(screen.getByRole("link", { name: "Read" }));
    assert.equal(screen.queryByTestId("stacks-card-footer"), null);
    assert.equal(screen.queryByText("The audiobook is wanted"), null);
    assert.equal(screen.queryByRole("button", { name: "Add to Wanted" }), null);
    assert.equal(screen.queryByRole("link", { name: "Find beyond" }), null);
  });

  it("leaves Listen off the Stacks poster when a companion audiobook is shelved", () => {
    renderCard(
      {
        ...book,
        audiobook: { applicable: true, shelved: { id: "audio-1", title: "The 1619 Project" }, find: {} },
      },
      { cardMode: "stacks" },
    );
    assert.ok(within(screen.getByTestId("stacks-card-footer")).getByText("Nikole Hannah-Jones"));
    assert.equal(screen.queryByRole("link", { name: "Listen" }), null);
    assert.equal(screen.queryByRole("link", { name: "Read" }), null);
    assert.equal(screen.queryByText("On the shelf"), null);
  });

  it("keeps On the shelf and Read when Stacks mode is off", () => {
    renderCard(book);
    assert.ok(screen.getByText("On the shelf"));
    assert.ok(screen.getByRole("link", { name: "Read" }));
    assert.equal(screen.queryByTestId("stacks-card-footer"), null);
  });

  it("keeps Read and Download in the grip, and a cover click still opens the peek", async () => {
    renderCard({ ...book, title: "<script>alert(1)</script>", author: "Nikole Hannah-Jones" }, { cardMode: "stacks" });
    const footer = screen.getByTestId("stacks-card-footer");
    assert.ok(within(footer).getByText("<script>alert(1)</script>"));
    assert.equal(footer.querySelector("script"), null);
    assert.equal(footer.querySelector("img"), null);

    await userEvent.click(screen.getByRole("button", { name: /Actions for/ }));
    assert.ok(await screen.findByRole("link", { name: "Read" }));
    assert.ok(screen.getByRole("link", { name: "Download" }));
    assert.equal(within(footer).queryByRole("link", { name: "Read" }), null);
    assert.equal(within(footer).queryByRole("link", { name: "Download" }), null);

    fireEvent.click(screen.getByRole("button", { name: /^<script>alert\(1\)<\/script>/ }));
    assert.ok(await screen.findByRole("dialog"));
    assert.equal(within(footer).queryByText("On the shelf"), null);
  });
});
