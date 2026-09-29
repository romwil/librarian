import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { test } from "node:test";
import {
  catchUpCtaLabel,
  catchUpInvitation,
  catchUpNoun,
  missingRibbonBeads,
} from "./lib/seriesCatchUp.js";

const root = dirname(fileURLToPath(import.meta.url));
const catchUpSrc = readFileSync(join(root, "components/SeriesCatchUp.jsx"), "utf8");
const hallSrc = readFileSync(join(root, "pages/HallPage.jsx"), "utf8");
const workSrc = readFileSync(join(root, "pages/WorkPage.jsx"), "utf8");
const motionSrc = readFileSync(join(root, "styles/motion.css"), "utf8");
const stylesSrc = readFileSync(join(root, "styles.css"), "utf8");

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

test("SeriesCatchUp keeps invitation voice and alive chrome", () => {
  assert.match(catchUpSrc, /data-testid="series-catch-up"/);
  assert.match(catchUpSrc, /aria-label="Series catch-up"/);
  assert.match(catchUpSrc, /A hole or two from whole/);
  assert.match(catchUpSrc, /No hurry/);
  assert.match(catchUpSrc, /series-catch-up-alive/);
  assert.match(catchUpSrc, /series-catch-up-glow/);
  assert.match(catchUpSrc, /cover-settle/);
  assert.match(catchUpSrc, /catchUpCtaLabel/);
  assert.match(catchUpSrc, /gapFindFields/);
});

test("SeriesCatchUp hides itself on empty payloads instead of half-painting", () => {
  assert.match(catchUpSrc, /catchUp\?\.series \|\| \[\]/);
  assert.match(catchUpSrc, /if \(!catchUp \|\| catchUp\.empty \|\| !series\.length\) return null;/);
});

test("SeriesCatchUp avoids KPI dashboard chrome", () => {
  assert.doesNotMatch(catchUpSrc, /owned_count/);
  assert.doesNotMatch(catchUpSrc, /missing_count/);
  assert.doesNotMatch(catchUpSrc, /bagging/i);
  assert.doesNotMatch(catchUpSrc, /streak|badge|score/i);
});

test("Hall mounts catch-up after Tonight’s Shelf", () => {
  assert.match(hallSrc, /import SeriesCatchUp from "\.\.\/components\/SeriesCatchUp\.jsx"/);
  const shelfAt = hallSrc.indexOf("<TonightShelf");
  const catchUpAt = hallSrc.indexOf("<SeriesCatchUp");
  assert.ok(shelfAt > -1 && catchUpAt > shelfAt, "catch-up must follow Tonight’s Shelf");
  assert.match(hallSrc, /catchUp=\{hall\?\.series_catch_up\}/);
  assert.match(hallSrc, /gapsLocal\(\)/);
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

test("catch-up motion honours prefers-reduced-motion", () => {
  assert.match(motionSrc, /\.series-catch-up-alive/);
  assert.match(motionSrc, /\.series-catch-up-glow\s*\{[^}]*shelf-breath/s);
  const reduced = motionSrc.slice(motionSrc.indexOf("prefers-reduced-motion"));
  assert.match(reduced, /\.series-catch-up,/);
  assert.match(reduced, /\.series-catch-up-glow,/);
  assert.match(reduced, /\.series-catch-up-invite,/);
  assert.match(reduced, /animation: none !important/);
});

test("catch-up surface borrows lamp atmosphere and gap beads", () => {
  assert.match(stylesSrc, /\.series-catch-up\s*\{/);
  assert.match(stylesSrc, /\.series-catch-up-invitation/);
  assert.match(stylesSrc, /\.series-catch-up-track \.series-bead/);
  assert.match(stylesSrc, /\.series-catch-up[\s\S]*var\(--lamp\)/);
});
