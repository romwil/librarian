import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import { livingJob } from "./lib/maintainDock.js";

const root = dirname(fileURLToPath(import.meta.url));
const hookSrc = readFileSync(join(root, "hooks/useProgressJob.js"), "utf8");
const dockSrc = readFileSync(join(root, "components/MaintainStatusDock.jsx"), "utf8");
const maintainSrc = readFileSync(join(root, "pages/MaintainPage.jsx"), "utf8");

test("useProgressJob pauses polling when the document is hidden", () => {
  assert.match(hookSrc, /visibilityState === "hidden"/);
  assert.match(hookSrc, /visibilitychange/);
  assert.match(hookSrc, /addEventListener\("visibilitychange"/);
  assert.match(hookSrc, /removeEventListener\("visibilitychange"/);
});

test("MaintainStatusDock uses a slower idle poll cadence", () => {
  assert.match(dockSrc, /idleMs:\s*dockIdleMs/);
  assert.match(dockSrc, /15_000|15000/);
  assert.match(dockSrc, /pollIdle:\s*true/);
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
