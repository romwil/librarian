// @vitest-environment jsdom
import assert from "node:assert/strict";
import { render, screen } from "@testing-library/react";
import { describe, it } from "vitest";
import JobProgress from "./components/JobProgress.jsx";

describe("JobProgress", () => {
  it("renders kicker, meter, and status line", () => {
    render(
      <JobProgress
        kicker="Clear extra-files progress"
        testId="review-extra-files-progress"
        phaseLabel="clearing"
        done={2}
        total={5}
        percent={40}
        statusLine="Clearing… 2 of 5"
        meterLabel="Clear extra-files progress"
        stats={["shelved 1"]}
      />,
    );
    const block = screen.getByTestId("review-extra-files-progress");
    const text = block.textContent;
    assert.match(text, /Clear extra-files progress/);
    assert.match(text, /clearing/);
    assert.match(text, /2 of 5/);
    assert.match(text, /40%/);
    assert.match(text, /shelved 1/);
    assert.match(text, /Clearing… 2 of 5/);
    assert.ok(screen.getByRole("progressbar"));
  });

  it("shows indeterminate meter when requested", () => {
    render(<JobProgress kicker="Shelving" testId="maintain-ingest-status" phaseLabel="scanning" indeterminate />);
    const block = screen.getByTestId("maintain-ingest-status");
    assert.ok(block.querySelector(".ingest-progress-meter--indeterminate"));
  });
});
