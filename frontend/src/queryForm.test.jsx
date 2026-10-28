// @vitest-environment jsdom
import assert from "node:assert/strict";
import { render, screen } from "@testing-library/react";
import { describe, it } from "vitest";
import QueryForm from "./components/QueryForm.jsx";
import { KINDS } from "./find.js";

const noop = () => {};

function renderForm(props) {
  return render(
    <QueryForm
      draft=""
      onDraft={noop}
      kind=""
      onKindCommit={noop}
      advanced={{}}
      onAdvanced={noop}
      onSubmit={noop}
      {...props}
    />,
  );
}

function optionValues(container) {
  return [...container.querySelectorAll("option")].map((option) => option.value);
}

function labels(container) {
  return [...container.querySelectorAll("label")].map((label) => label.textContent.trim());
}

describe("QueryForm kinds", () => {
  it("puts a custom kinds list in the search select", () => {
    const kinds = [
      ["", "Everything"],
      ["book", "Book"],
      ["zine", "Zine"],
    ];
    const { container } = renderForm({ variant: "search", kinds });
    assert.deepEqual(
      optionValues(container),
      kinds.map(([value]) => value),
    );
    assert.ok([...container.querySelectorAll("option")].some((option) => option.textContent === "Zine"));
  });

  it("keeps default Librarian kinds in the search select", () => {
    const { container } = renderForm({ variant: "search" });
    assert.deepEqual(
      optionValues(container),
      KINDS.map(([value]) => value),
    );
    assert.equal(optionValues(container).includes("movie"), false);
  });

  it("morphs Search advanced fields with the kind chip", () => {
    const music = renderForm({ variant: "search", kind: "music" });
    const advanced = screen.getByTestId("search-advanced");
    assert.equal(advanced.dataset.kind, "music");
    let names = labels(music.container);
    for (const name of ["Artist", "Album", "Year"]) assert.ok(names.includes(name), name);
    for (const name of ["ISBN", "Author", "Series"]) assert.equal(names.includes(name), false, name);
    assert.ok(screen.getAllByRole("combobox").length > 0);
    assert.equal(advanced.querySelector("summary").textContent.trim(), "More ways to search");
    assert.equal(music.container.textContent.includes("Advanced"), false);
    assert.equal(music.container.textContent.includes("same page"), false);
    assert.ok(screen.getByRole("search"));
    assert.ok(screen.getByRole("button", { name: "Search" }));
    music.unmount();

    const comic = renderForm({ variant: "search", kind: "comic" });
    assert.equal(screen.getByTestId("search-advanced").dataset.kind, "comic");
    names = labels(comic.container);
    assert.ok(names.includes("Series"));
    assert.ok(names.includes("Issue"));
    assert.equal(names.includes("ISBN"), false);
    assert.equal(names.includes("Artist"), false);
    comic.unmount();

    const book = renderForm({ variant: "search", kind: "book" });
    names = labels(book.container);
    for (const name of ["Title", "Author", "ISBN"]) assert.ok(names.includes(name), name);
    assert.equal(names.includes("Artist"), false);
    book.unmount();

    const audio = renderForm({ variant: "search", kind: "audiobook" });
    names = labels(audio.container);
    for (const name of ["Title", "Author", "ISBN"]) assert.ok(names.includes(name), name);
    assert.equal(names.includes("Album"), false);
    audio.unmount();

    const all = renderForm({ variant: "search", kind: "" });
    assert.equal(screen.getByTestId("search-advanced").dataset.kind, "all");
    names = labels(all.container);
    assert.equal(names.includes("ISBN"), false);
    assert.equal(names.includes("Artist"), false);
  });

  it("morphs Find fields the same way without the Advanced shell", () => {
    const { container } = renderForm({ variant: "find", kind: "music" });
    const fields = screen.getByTestId("find-fields");
    assert.equal(fields.dataset.kind, "music");
    const names = labels(container);
    assert.ok(names.includes("Artist"));
    assert.ok(names.includes("Album"));
    assert.equal(screen.queryByTestId("search-advanced"), null);
    assert.equal(names.includes("ISBN"), false);
  });

  it("can open More ways to search instead of leaving fields closed", () => {
    const closed = renderForm({ variant: "search", kind: "book" });
    assert.equal(screen.getByTestId("search-advanced").open, false);
    closed.unmount();
    const opened = renderForm({ variant: "search", kind: "book", advancedOpen: true });
    assert.equal(screen.getByTestId("search-advanced").open, true);
    const names = labels(opened.container);
    for (const name of ["Title", "Author", "ISBN"]) assert.ok(names.includes(name), name);
  });

  it("hero variant is just the field", () => {
    const { container } = renderForm({ variant: "hero", placeholder: "Title, author, or ISBN" });
    assert.ok(screen.getByRole("search"));
    assert.ok(screen.getByPlaceholderText("Title, author, or ISBN"));
    assert.ok(screen.getByRole("button", { name: "Search" }));
    assert.equal(container.querySelector(".search-compose-chips"), null);
    assert.equal(screen.queryByTestId("search-advanced"), null);
    assert.equal(container.textContent.includes("More ways to search"), false);
  });
});
