import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "vitest";
import {
  catchUpCtaLabel,
  catchUpInvitation,
  catchUpNoun,
  missingRibbonBeads,
} from "./lib/seriesCatchUp.js";
import { readStyles } from "./test/styles.js";

const root = dirname(fileURLToPath(import.meta.url));
const hallSrc = readFileSync(join(root, "pages/HallPage.jsx"), "utf8");
const workSrc = readFileSync(join(root, "pages/WorkPage.jsx"), "utf8");
const motionSrc = readFileSync(join(root, "styles/motion.css"), "utf8");
const stylesSrc = readStyles();

test("catch-up nouns follow the shelf, not generic items", () => {
  assert.equal(catchUpNoun("comic"), "issue");
  assert.equal(catchUpNoun("comic", "", true), "issues");
  assert.equal(catchUpNoun("magazine"), "issue");
  assert.equal(catchUpNoun("music", "music_album", true), "albums");
  assert.equal(catchUpNoun("audiobook", "multipart"), "part");
  assert.equal(catchUpNoun("book"), "volume");
  assert.equal(catchUpNoun("", "", true), "volumes");
});

test("invitation copy counts in words and never scores the household", () => {
  assert.equal(
    catchUpInvitation({ seriesName: "Saga", kind: "comic", missingCount: 1 }),
    "One issue from a whole Saga.",
  );
  assert.equal(
    catchUpInvitation({ seriesName: "Saga", kind: "comic", missingCount: 2 }),
    "Two issues from a whole Saga.",
  );
  assert.equal(
    catchUpInvitation({ seriesName: "Saga", kind: "comic", missingCount: 9 }),
    "A few issues from a whole Saga.",
  );
  assert.equal(catchUpInvitation({ kind: "book", missingCount: 1 }), "One volume from a whole run.");
});

test("invitation stays silent with nothing missing or hostile counts", () => {
  assert.equal(catchUpInvitation({ seriesName: "Saga", kind: "comic", missingCount: 0 }), "");
  assert.equal(catchUpInvitation({ seriesName: "Saga", missingCount: -3 }), "");
  assert.equal(catchUpInvitation({ seriesName: "Saga", missingCount: "junk" }), "");
  assert.equal(catchUpInvitation(), "");
});

test("invitation trims and keeps a hostile series name inert as text", () => {
  assert.equal(
    catchUpInvitation({ seriesName: "  <script>x</script>  ", kind: "comic", missingCount: 1 }),
    "One issue from a whole <script>x</script>.",
  );
});

test("reader CTA asks the house; owner and op go to Find", () => {
  assert.equal(catchUpCtaLabel("reader"), "Ask the house");
  assert.equal(catchUpCtaLabel(), "Ask the house");
  assert.equal(catchUpCtaLabel("owner"), "Find this hole");
  assert.equal(catchUpCtaLabel("op"), "Find this hole");
});

test("only ribbon holes count as catch-up, malformed beads ignored", () => {
  const ribbon = [
    { value: "1", state: "owned" },
    { value: "2", state: "missing" },
    { value: "3", state: "current" },
    { value: "4", state: "missing" },
    null,
    "nonsense",
  ];
  assert.deepEqual(
    missingRibbonBeads(ribbon).map((bead) => bead.value),
    ["2", "4"],
  );
  assert.deepEqual(missingRibbonBeads(), []);
  assert.deepEqual(missingRibbonBeads("nope"), []);
});

test("Hall continue rails stay in reading order", () => {
  const listenAt = hallSrc.indexOf('title="Continue listening"');
  const readAt = hallSrc.indexOf('title="Continue reading"');
  const recentAt = hallSrc.indexOf('title="Recently added"');
  const favoritesAt = hallSrc.indexOf('title="Favorites"');
  assert.ok(listenAt > -1 && readAt > listenAt, "Continue reading follows Continue listening");
  assert.ok(recentAt > readAt, "Recently added follows Continue reading");
  assert.ok(favoritesAt > recentAt, "Favorites follows Recently added");
});

test("Work soft invite rides the series ribbon", () => {
  assert.match(workSrc, /data-testid="series-catch-up-invite"/);
  assert.match(workSrc, /missingRibbonBeads\(data\.series_ribbon\)/);
  assert.match(workSrc, /catchUpInvitation\(\{/);
  assert.match(workSrc, /catchUpCtaLabel\(user\?\.role\)/);
  const ribbonAt = workSrc.indexOf('data-testid="series-ribbon"');
  const inviteAt = workSrc.indexOf('data-testid="series-catch-up-invite"');
  assert.ok(ribbonAt > -1 && inviteAt > ribbonAt, "invite must sit inside the series spine");
});

test("series invite motion honours prefers-reduced-motion", () => {
  assert.match(motionSrc, /\.series-catch-up-invite\s*\{[^}]*soft-enter/s);
  const reduced = motionSrc.slice(motionSrc.indexOf("prefers-reduced-motion"));
  assert.match(reduced, /\.series-catch-up-invite,/);
  assert.match(reduced, /animation: none !important/);
});

test("work page invite keeps its surface styles", () => {
  assert.match(stylesSrc, /\.series-catch-up-invite\s*\{/);
});
