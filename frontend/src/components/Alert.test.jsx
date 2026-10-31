// @vitest-environment jsdom
import assert from "node:assert/strict";
import { render, screen } from "@testing-library/react";
import { describe, it } from "vitest";
import Alert from "./Alert.jsx";

describe("Alert", () => {
  it("announces errors assertively", () => {
    render(<Alert>{"That name and password don't match."}</Alert>);
    const node = screen.getByRole("alert");
    assert.equal(node.getAttribute("aria-live"), "assertive");
    assert.match(node.textContent, /don't match/);
  });

  it("announces quiet status politely", () => {
    render(<Alert tone="status">Copied.</Alert>);
    const node = screen.getByRole("status");
    assert.equal(node.getAttribute("aria-live"), "polite");
  });
});
