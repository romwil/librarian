// @vitest-environment jsdom
import assert from "node:assert/strict";
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it } from "vitest";
import SearchModeControl, { SEARCH_MODES } from "./components/SearchModeControl.jsx";

describe("search mode control", () => {
  it("offers title, author, ISBN, series, and narrator as one choice", async () => {
    const picked = [];
    render(<SearchModeControl mode="isbn" onMode={(value) => picked.push(value)} />);
    assert.equal(SEARCH_MODES.length, 5);
    const group = screen.getByRole("radiogroup", { name: "Search mode" });
    for (const [value, label] of SEARCH_MODES) {
      const radio = within(group).getByRole("radio", { name: label });
      assert.equal(radio.dataset.testid, `search-mode-${value}`);
    }
    assert.equal(within(group).getByRole("radio", { name: "ISBN" }).getAttribute("aria-checked"), "true");
    assert.equal(within(group).getByRole("radio", { name: "Title" }).getAttribute("aria-checked"), "false");
    await userEvent.click(within(group).getByRole("radio", { name: "Title" }));
    assert.deepEqual(picked, ["title"]);
  });
});
