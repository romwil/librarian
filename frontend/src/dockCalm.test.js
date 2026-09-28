import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";

const root = dirname(fileURLToPath(import.meta.url));
const hookSrc = readFileSync(join(root, "hooks/useProgressJob.js"), "utf8");
const dockSrc = readFileSync(join(root, "components/MaintainStatusDock.jsx"), "utf8");

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
