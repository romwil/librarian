import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import {
  pulseClass,
  scoreIsCalm,
  scorePresence,
  scoreTend,
} from "./lib/shelfHealthScore.js";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

describe("shelf health score", () => {
  it("keeps presence warm when the server is quiet", () => {
    assert.match(scorePresence({ pulse: "calm" }), /settled/i);
    assert.match(scorePresence({ pulse: "stirring" }), /breeze|stacks/i);
    assert.match(scorePresence({ pulse: "needs_you" }), /locked/i);
    assert.match(scorePresence({ presence: "Custom weather." }), /Custom weather/);
  });

  it("exposes one tend action without inventing KPIs", () => {
    assert.equal(scoreTend(null), null);
    assert.equal(scoreTend({ tend: { cta: "Purge shells" } }), null);
    const tend = scoreTend({
      tend: { cta: "Purge shells", href: "/maintain#maintain-shells", kind: "unshelved_shells" },
    });
    assert.equal(tend.cta, "Purge shells");
    assert.equal(scoreIsCalm({ pulse: "calm", ok: true }), true);
    assert.equal(scoreIsCalm({ pulse: "stirring", tend }), false);
  });

  it("maps pulse to chrome classes without numeric grades", () => {
    assert.equal(pulseClass({ pulse: "needs_you" }), "needs_you");
    assert.equal(pulseClass({ pulse: "stirring" }), "stirring");
    assert.equal(pulseClass({ pulse: "A+" }), "calm");
  });

  it("ShelfHealthPulse ships weather chrome, not a scoreboard", () => {
    const src = readFileSync(join(root, "src/components/ShelfHealthPulse.jsx"), "utf8");
    assert.match(src, /shelf-health-pulse/);
    assert.match(src, /data-testid="shelf-health-pulse"/);
    assert.doesNotMatch(src, /percent|scoreboard|grade/i);
  });

  it("Maintain mounts the pulse inside Shelf health", () => {
    const page = readFileSync(join(root, "src/pages/MaintainPage.jsx"), "utf8");
    assert.match(page, /ShelfHealthPulse/);
    assert.match(page, /shelfHealth\.score/);
  });

  it("motion and styles honour reduced-motion for the pulse", () => {
    const motion = readFileSync(join(root, "src/styles/motion.css"), "utf8");
    const styles = readFileSync(join(root, "src/styles.css"), "utf8");
    assert.match(styles, /\.shelf-health-pulse/);
    assert.match(motion, /shelf-health-pulse/);
    assert.match(motion, /prefers-reduced-motion/);
  });
});
