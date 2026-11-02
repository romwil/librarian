// @vitest-environment jsdom
import assert from "node:assert/strict";
import { act, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, it, vi } from "vitest";
import Reader from "./Reader.jsx";
import { READER_OPEN_TIMEOUT_MS } from "../reader.js";

describe("Reading Room open", () => {
  beforeEach(() => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => ({ matches: true, addEventListener() {}, removeEventListener() {} })),
    );
    vi.stubGlobal(
      "fetch",
      vi.fn(() => new Promise(() => {})),
    );
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("replaces Opening the volume with a failure when the file never arrives", async () => {
    vi.useFakeTimers();
    render(
      <Reader
        work={{ id: "stuck", title: "A Well Trained Wife" }}
        files={[{ id: "e1", filename: "A Well Trained Wife.epub", reading_room: true }]}
        onClose={() => {}}
      />,
    );
    assert.ok(screen.getByText("Opening the volume…"));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(READER_OPEN_TIMEOUT_MS);
    });
    assert.equal(screen.queryByText("Opening the volume…"), null);
    assert.match(screen.getByRole("alert").textContent, /took too long to open/i);
  });
});
