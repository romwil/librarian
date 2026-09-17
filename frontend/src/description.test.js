import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { looksLikeHtml, sanitizeDescriptionHtml } from "./description.js";

describe("description HTML", () => {
  it("detects HTML-ish blurbs", () => {
    assert.equal(looksLikeHtml("<p>King Tut</p>"), true);
    assert.equal(looksLikeHtml("A winter planet."), false);
  });

  it("keeps allowlisted tags and strips scripts", () => {
    const cleaned = sanitizeDescriptionHtml(
      '<h3>Overview</h3><p class="x">A <em>tomb</em></p><script>alert(1)</script><iframe src="x"></iframe>',
    );
    assert.match(cleaned, /<h3>Overview<\/h3>/);
    assert.match(cleaned, /<em>tomb<\/em>/);
    assert.equal(/script|iframe|class=/i.test(cleaned), false);
  });
});
