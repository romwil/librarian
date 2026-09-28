import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import {
  briefIsEmpty,
  briefPresence,
  morningTendPresence,
  rankMorningKinds,
} from "./lib/morningBrief.js";

const root = dirname(fileURLToPath(import.meta.url));
const briefSrc = readFileSync(join(root, "components/MorningBrief.jsx"), "utf8");
const maintainSrc = readFileSync(join(root, "pages/MaintainPage.jsx"), "utf8");
const motionSrc = readFileSync(join(root, "styles/motion.css"), "utf8");
const stylesSrc = readFileSync(join(root, "styles.css"), "utf8");
const apiSrc = readFileSync(join(root, "api.js"), "utf8");

test("presence counts in words — never a KPI strip", () => {
  assert.equal(morningTendPresence(0), "The shelves are quiet this morning.");
  assert.equal(morningTendPresence(1), "Tend this one.");
  assert.equal(morningTendPresence(2), "Tend these two.");
  assert.equal(morningTendPresence(3), "Tend these three.");
  assert.equal(morningTendPresence(11), "Tend these few.");
  assert.equal(morningTendPresence("junk"), "The shelves are quiet this morning.");
  assert.equal(morningTendPresence(-4), "The shelves are quiet this morning.");
});

test("briefPresence prefers server copy and recovers from hostile payloads", () => {
  assert.equal(briefPresence({ presence: "Tend these two." }), "Tend these two.");
  assert.equal(briefPresence({ items: [{ id: "a" }] }), "Tend this one.");
  assert.equal(briefPresence(null), "The shelves are quiet this morning.");
  assert.equal(briefPresence({ items: "nope" }), "The shelves are quiet this morning.");
});

test("briefIsEmpty treats missing and empty lists as quiet", () => {
  assert.equal(briefIsEmpty(null), true);
  assert.equal(briefIsEmpty({ empty: true, items: [{ id: "x" }] }), true);
  assert.equal(briefIsEmpty({ items: [] }), true);
  assert.equal(briefIsEmpty({ empty: false, items: [{ id: "x" }] }), false);
});

test("rankMorningKinds prefers locked roots then Holds desk", () => {
  assert.deepEqual(
    rankMorningKinds({
      comic_book_blends: 9,
      unshelved_shells: 4,
      extra_files: 3,
      holds_desk: 2,
      shelf_health: 1,
    }),
    ["shelf_health", "holds_desk", "extra_files"],
  );
});

test("MorningBrief is alive — glow, settle, breathing, Holds lexicon", () => {
  assert.match(briefSrc, /morning-brief-alive/);
  assert.match(briefSrc, /morning-brief-glow/);
  assert.match(briefSrc, /cover-settle/);
  assert.match(briefSrc, /is-breathing/);
  assert.match(briefSrc, /Tend these three/);
  assert.match(briefSrc, /Morning desk/);
  assert.match(briefSrc, /data-testid="morning-brief"/);
  assert.match(briefSrc, /itemLabel|item\.label/);
  assert.doesNotMatch(briefSrc, /bagging/i);
  assert.doesNotMatch(briefSrc, /\bKPI\b/);
});

test("Maintain mounts morning brief above the dock", () => {
  assert.match(maintainSrc, /MorningBrief/);
  assert.match(maintainSrc, /maintainMorningBrief/);
  assert.match(apiSrc, /maintainMorningBrief/);
  assert.match(maintainSrc, /Holds desk/);
  assert.doesNotMatch(maintainSrc, /Review bag|bagging/i);
  const briefAt = maintainSrc.indexOf("<MorningBrief");
  const dockAt = maintainSrc.indexOf("<MaintainStatusDock");
  assert.ok(briefAt > 0 && dockAt > briefAt, "brief should render before the status dock");
});

test("morning brief motion respects reduced-motion and keeps presence", () => {
  assert.match(motionSrc, /\.morning-brief-glow/);
  assert.match(motionSrc, /\.morning-brief-row\.is-breathing::before/);
  assert.match(motionSrc, /prefers-reduced-motion:\s*reduce/);
  const reduced = motionSrc.slice(motionSrc.indexOf("prefers-reduced-motion"));
  assert.match(reduced, /\.morning-brief,/);
  assert.match(reduced, /\.morning-brief-glow,/);
  assert.match(stylesSrc, /\.morning-brief\s*\{/);
  assert.match(stylesSrc, /morning-brief-list/);
});
