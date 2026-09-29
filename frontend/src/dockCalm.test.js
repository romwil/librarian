import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import {
  MAINTAIN_JOBS_WAKE,
  anyMaintainJobRunning,
  livingJob,
  nextProgressPollWait,
} from "./lib/maintainDock.js";

const root = dirname(fileURLToPath(import.meta.url));
const hookSrc = readFileSync(join(root, "hooks/useProgressJob.js"), "utf8");
const dockSrc = readFileSync(join(root, "components/MaintainStatusDock.jsx"), "utf8");
const maintainSrc = readFileSync(join(root, "pages/MaintainPage.jsx"), "utf8");
const apiSrc = readFileSync(join(root, "api.js"), "utf8");

test("useProgressJob pauses polling when the document is hidden", () => {
  assert.match(hookSrc, /visibilityState === "hidden"/);
  assert.match(hookSrc, /visibilitychange/);
  assert.match(hookSrc, /addEventListener\("visibilitychange"/);
  assert.match(hookSrc, /removeEventListener\("visibilitychange"/);
});

test("useProgressJob supports probe-only mode without idle cadence", () => {
  assert.match(hookSrc, /probe\s*=\s*false/);
  assert.match(hookSrc, /wakeEvent/);
  assert.match(hookSrc, /nextProgressPollWait/);
  assert.match(hookSrc, /!active && !pollIdle && !probe/);
});

test("MaintainStatusDock multiplexes jobs status and does not idle four-poll", () => {
  assert.match(dockSrc, /api\.maintainJobsStatus/);
  assert.match(dockSrc, /pollIdle:\s*false/);
  assert.match(dockSrc, /probe:\s*true/);
  assert.match(dockSrc, /wakeEvent:\s*MAINTAIN_JOBS_WAKE/);
  assert.match(dockSrc, /anyMaintainJobRunning/);
  assert.doesNotMatch(dockSrc, /pollIdle:\s*true/);
  assert.doesNotMatch(dockSrc, /api\.scanStatus/);
  assert.doesNotMatch(dockSrc, /api\.enrichStatus/);
  assert.doesNotMatch(dockSrc, /api\.ingestStatus/);
  assert.doesNotMatch(dockSrc, /api\.reviewReprocessExtraFilesStatus/);
  assert.match(apiSrc, /maintainJobsStatus:\s*\(\)\s*=>\s*request\("\/maintain\/jobs\/status"\)/);
});

test("Maintain page wakes the dock when owner starts a job", () => {
  assert.match(maintainSrc, /wakeMaintainJobs/);
  assert.match(maintainSrc, /setScanning\(true\);\s*\n\s*wakeMaintainJobs/);
  assert.match(maintainSrc, /setEnriching\(true\);\s*\n\s*wakeMaintainJobs/);
  assert.match(maintainSrc, /setExtraClearing\(true\);\s*\n\s*wakeMaintainJobs/);
});

test("livingJob only keeps running jobs — idle completed chips collapse", () => {
  const running = (s) => String(s?.status || "") === "running";
  assert.equal(livingJob(null, running), false);
  assert.equal(livingJob({ status: "running" }, running), true);
  assert.equal(livingJob({ status: "completed" }, running), false);
  assert.equal(livingJob({ status: "failed" }, running), false);
  assert.equal(livingJob({ status: "idle" }, running), false);
  assert.match(dockSrc, /livingJob\(/);
  assert.match(dockSrc, /if \(!cards\.length\) return null/);
  assert.doesNotMatch(dockSrc, /maintain-status-idle/);
  assert.doesNotMatch(dockSrc, /status\.status === "completed"/);
});

test("anyMaintainJobRunning reads multiplex bundle keys", () => {
  assert.equal(anyMaintainJobRunning(null), false);
  assert.equal(anyMaintainJobRunning({}), false);
  assert.equal(
    anyMaintainJobRunning({
      scan: { status: "idle" },
      enrich: { status: "completed" },
      ingest: { status: "failed" },
      extra_files: { status: "idle" },
    }),
    false,
  );
  assert.equal(
    anyMaintainJobRunning({
      scan: { status: "running" },
      enrich: { status: "idle" },
      ingest: { status: "idle" },
      extra_files: { status: "idle" },
    }),
    true,
  );
  assert.equal(
    anyMaintainJobRunning({
      scan: { status: "idle" },
      enrich: { status: "idle" },
      ingest: { status: "idle" },
      extra_files: { status: "running" },
    }),
    true,
  );
  assert.equal(MAINTAIN_JOBS_WAKE, "librarian:maintain-jobs-wake");
});

test("nextProgressPollWait stops when idle without pollIdle", () => {
  assert.equal(
    nextProgressPollWait({ live: true, active: false, pollIdle: false, liveMs: 700, idleMs: 15000 }),
    700,
  );
  assert.equal(
    nextProgressPollWait({ live: false, active: true, pollIdle: false, liveMs: 700, idleMs: 15000 }),
    700,
  );
  assert.equal(
    nextProgressPollWait({ live: false, active: false, pollIdle: true, liveMs: 700, idleMs: 15000 }),
    15000,
  );
  assert.equal(
    nextProgressPollWait({ live: false, active: false, pollIdle: false, liveMs: 700, idleMs: 15000 }),
    null,
  );
});

test("Maintain progressive-loads desk cards instead of one fan-out", () => {
  assert.match(maintainSrc, /Progressive load/);
  assert.match(maintainSrc, /Wave 1/);
  assert.match(maintainSrc, /Wave 2/);
  assert.match(maintainSrc, /Wave 3/);
  assert.match(maintainSrc, /later\(80,/);
  assert.match(maintainSrc, /later\(160,/);
  // Idle start — chrome paints before morning/indexer skeletons.
  assert.match(maintainSrc, /morningBriefLoading, setMorningBriefLoading\] = useState\(false\)/);
  assert.match(maintainSrc, /indexerCardLoading, setIndexerCardLoading\] = useState\(false\)/);
});
