import assert from "node:assert/strict";
import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, it } from "node:test";
import * as esbuild from "esbuild";

const frontendRoot = fileURLToPath(new URL("..", import.meta.url));

async function loadJobProgress() {
  const cache = join(frontendRoot, "node_modules/.cache");
  mkdirSync(cache, { recursive: true });
  const outfile = join(cache, "librarian-jobprogress-test.mjs");
  await esbuild.build({
    absWorkingDir: frontendRoot,
    entryPoints: ["src/components/JobProgress.jsx"],
    bundle: true,
    format: "esm",
    outfile,
    jsx: "automatic",
    platform: "node",
    packages: "external",
  });
  return (await import(pathToFileURL(outfile).href)).default;
}

describe("JobProgress", () => {
  it("renders kicker, meter, and status line", async () => {
    const JobProgress = await loadJobProgress();
    const html = renderToStaticMarkup(
      createElement(JobProgress, {
        kicker: "Clear extra-files progress",
        testId: "review-extra-files-progress",
        phaseLabel: "clearing",
        done: 2,
        total: 5,
        percent: 40,
        statusLine: "Clearing… 2 of 5",
        meterLabel: "Clear extra-files progress",
        stats: ["shelved 1"],
      }),
    );
    assert.match(html, /data-testid="review-extra-files-progress"/);
    assert.match(html, /Clear extra-files progress/);
    assert.match(html, /clearing/);
    assert.match(html, /2 of 5/);
    assert.match(html, /40%/);
    assert.match(html, /shelved 1/);
    assert.match(html, /role="progressbar"/);
    assert.match(html, /Clearing… 2 of 5/);
  });

  it("shows indeterminate meter when requested", async () => {
    const JobProgress = await loadJobProgress();
    const html = renderToStaticMarkup(
      createElement(JobProgress, {
        kicker: "Shelving",
        testId: "maintain-ingest-status",
        phaseLabel: "scanning",
        indeterminate: true,
      }),
    );
    assert.match(html, /ingest-progress-meter--indeterminate/);
  });
});
