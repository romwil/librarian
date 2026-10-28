// @vitest-environment jsdom
import assert from "node:assert/strict";
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, it, vi } from "vitest";
import { THINKING_LONG_AFTER_MS, Thinking } from "./Thinking.jsx";

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

it("says Still thinking after a long wait", () => {
  render(<Thinking />);
  const status = screen.getByRole("status");
  assert.match(status.textContent, /Thinking…/);
  assert.doesNotMatch(status.textContent, /Still thinking/);
  act(() => {
    vi.advanceTimersByTime(THINKING_LONG_AFTER_MS - 1);
  });
  assert.doesNotMatch(screen.getByRole("status").textContent, /Still thinking/);
  act(() => {
    vi.advanceTimersByTime(1);
  });
  assert.match(screen.getByRole("status").textContent, /Still thinking…/);
  assert.equal(screen.getByRole("status").getAttribute("role"), "status");
});
