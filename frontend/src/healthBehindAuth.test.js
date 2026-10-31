import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { describe, it } from "vitest";

const srcDir = path.dirname(new URL(import.meta.url).pathname);

describe("health behind auth (BD-5)", () => {
  it("WhatsNewGate keys off features version, not public health", () => {
    const src = fs.readFileSync(path.join(srcDir, "components/WhatsNewGate.jsx"), "utf8");
    assert.match(src, /api\.features\(\)/);
    assert.doesNotMatch(src, /api\.health\(\)/);
    assert.match(src, /user\?\.role === "owner" \|\| user\?\.role === "op"/);
  });

  it("AboutPanel reads owner /api/status for version and rev", () => {
    const src = fs.readFileSync(path.join(srcDir, "components/AboutPanel.jsx"), "utf8");
    assert.match(src, /\.status\(\)/);
    assert.doesNotMatch(src, /api\.health\(\)/);
  });

  it("api client exposes status", () => {
    const src = fs.readFileSync(path.join(srcDir, "api.js"), "utf8");
    assert.match(src, /status:\s*\(\)\s*=>\s*request\("\/status"\)/);
  });
});
