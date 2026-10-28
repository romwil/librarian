// @vitest-environment jsdom
import assert from "node:assert/strict";
import { useState } from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it } from "vitest";
import TypeaheadField, { isTypeaheadField } from "./components/TypeaheadField.jsx";

describe("TypeaheadField", () => {
  it("exports typeahead field allowlist", () => {
    assert.equal(isTypeaheadField("author"), true);
    assert.equal(isTypeaheadField("artist"), true);
    assert.equal(isTypeaheadField("album"), true);
    assert.equal(isTypeaheadField("year"), true);
    assert.equal(isTypeaheadField("q"), true);
    assert.equal(isTypeaheadField("isbn"), false);
    assert.equal(isTypeaheadField("issue"), false);
  });

  it("renders a combobox that keeps freeform value", async () => {
    function Harness() {
      const [value, setValue] = useState("Frank");
      return (
        <TypeaheadField
          id="ta-author"
          field="author"
          kind="book"
          value={value}
          onChange={setValue}
          onEnterSubmit={() => {}}
        />
      );
    }
    render(<Harness />);
    const box = screen.getByRole("combobox");
    assert.equal(box.value, "Frank");
    assert.equal(box.getAttribute("aria-autocomplete"), "list");
    await userEvent.type(box, "ie Herbert");
    assert.equal(box.value, "Frankie Herbert");
  });
});
