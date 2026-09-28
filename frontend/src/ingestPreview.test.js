import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import {
  ingestPreviewIsEmpty,
  ingestPreviewPresence,
  ingestPreviewVolumes,
  volumeIsTwin,
  volumeKindLabel,
  volumeStem,
} from "./lib/ingestPreview.js";

const root = dirname(fileURLToPath(import.meta.url));
const mapSrc = readFileSync(join(root, "components/IngestPreviewMap.jsx"), "utf8");
const addSrc = readFileSync(join(root, "components/AddToLibrary.jsx"), "utf8");
const motionSrc = readFileSync(join(root, "styles/motion.css"), "utf8");
const stylesSrc = readFileSync(join(root, "styles.css"), "utf8");
const apiSrc = readFileSync(join(root, "api.js"), "utf8");

test("presence prefers server copy and recovers from hostile payloads", () => {
  assert.equal(ingestPreviewPresence({ presence: "Two volumes wait on the map." }), "Two volumes wait on the map.");
  assert.equal(ingestPreviewPresence({ volumes_found: 1 }), "One volume waits on the map.");
  assert.equal(ingestPreviewPresence({ volumes_found: 0 }), "Nothing to shelve here — empty or only junk.");
  assert.equal(ingestPreviewPresence(null), "Nothing to shelve here — empty or only junk.");
  assert.equal(ingestPreviewPresence({ volumes_found: "nope" }), "Nothing to shelve here — empty or only junk.");
});

test("empty and volume helpers stay defensive", () => {
  assert.equal(ingestPreviewIsEmpty(null), true);
  assert.equal(ingestPreviewIsEmpty({ empty: true, volumes: [{ id: "x" }] }), true);
  assert.equal(ingestPreviewIsEmpty({ volumes_found: 0, volumes: [] }), true);
  assert.equal(ingestPreviewIsEmpty({ volumes_found: 2, volumes: [{ stem: "A" }] }), false);
  assert.deepEqual(ingestPreviewVolumes({ volumes: [{ stem: "A" }] }), [{ stem: "A" }]);
  assert.deepEqual(ingestPreviewVolumes({ volumes: "nope" }), []);
  assert.equal(volumeStem({ stem: "Dune" }), "Dune");
  assert.equal(volumeStem({}), "Untitled");
  assert.equal(volumeKindLabel({ kind_label: "Comic" }), "Comic");
  assert.equal(volumeKindLabel({ kind: "book" }), "Book");
  assert.equal(volumeIsTwin({ twin: true }), true);
  assert.equal(volumeIsTwin({ role: "twin" }), true);
  assert.equal(volumeIsTwin({ role: "ready" }), false);
});

test("IngestPreviewMap is alive — glow, settle, twin breath, Look first", () => {
  assert.match(mapSrc, /ingest-preview-alive/);
  assert.match(mapSrc, /ingest-preview-glow/);
  assert.match(mapSrc, /Look first/);
  assert.match(mapSrc, /Quiet map/);
  assert.match(mapSrc, /is-breathing/);
  assert.match(mapSrc, /data-testid="ingest-preview-map"/);
  assert.match(mapSrc, /data-testid="ingest-preview-volume"/);
});

test("AddToLibrary mounts Look first before Add", () => {
  assert.match(addSrc, /IngestPreviewMap/);
  assert.match(addSrc, /ingestPreview/);
  assert.match(addSrc, /ingest-look-first/);
  assert.match(addSrc, /Look first/);
  assert.match(apiSrc, /ingestPreview/);
  const lookAt = addSrc.indexOf("ingest-look-first");
  const addAt = addSrc.indexOf('data-testid="ingest-add"');
  assert.ok(lookAt > 0 && addAt > lookAt);
});

test("ingest preview motion respects reduced-motion and keeps presence", () => {
  assert.match(motionSrc, /\.ingest-preview-glow/);
  assert.match(motionSrc, /\.ingest-preview-row\.is-breathing::before/);
  const reduced = motionSrc.slice(motionSrc.indexOf("prefers-reduced-motion"));
  assert.match(reduced, /\.ingest-preview-map,/);
  assert.match(reduced, /\.ingest-preview-glow,/);
  assert.match(stylesSrc, /\.ingest-preview-map\s*\{/);
  assert.match(stylesSrc, /ingest-preview-list/);
});
