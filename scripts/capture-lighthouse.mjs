#!/usr/bin/env node
/**
 * PERF-003 — capture Lighthouse LCP/INP/CLS for Hall + Search.
 *
 * Usage (owner session already available, or foyer-only without cookie):
 *   BASE_URL=http://10.10.1.202:8793 \
 *   COOKIE='session=...' \
 *   node scripts/capture-lighthouse.mjs
 *
 * Writes JSON under docs/reviews/2026-11-04/perf-003-lighthouse/.
 * Requires: npx lighthouse (downloads on first run). Does not fail CI.
 */
import { mkdir, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";

const __dirname = dirname(fileURLToPath(import.meta.url));
const root = join(__dirname, "..");
const outDir = join(root, "docs/reviews/2026-11-04/perf-003-lighthouse");
const base = (process.env.BASE_URL || "http://10.10.1.202:8793").replace(/\/$/, "");
const cookie = process.env.COOKIE || "";
const stamp = new Date().toISOString().slice(0, 10);

const targets = [
  { id: "hall", path: "/", formFactor: "desktop" },
  { id: "hall-390", path: "/", formFactor: "mobile", width: 390, height: 844 },
  { id: "search", path: "/search", formFactor: "desktop" },
  { id: "search-390", path: "/search", formFactor: "mobile", width: 390, height: 844 },
];

await mkdir(outDir, { recursive: true });

const summary = {
  captured_at: new Date().toISOString(),
  base_url: base,
  cookie_present: Boolean(cookie),
  note: "Median of three runs preferred; this script stores one run per target. Auth cookie required for signed-in Hall/Search LCP.",
  runs: [],
};

for (const target of targets) {
  const outPath = join(outDir, `${stamp}-${target.id}.json`);
  const args = [
    "lighthouse",
    `${base}${target.path}`,
    "--only-categories=performance",
    "--output=json",
    `--output-path=${outPath}`,
    "--chrome-flags=--headless=new --no-sandbox",
    "--quiet",
  ];
  if (target.formFactor === "desktop") {
    args.push("--preset=desktop");
  } else {
    args.push(
      "--form-factor=mobile",
      `--screenEmulation.mobile`,
      `--screenEmulation.width=${target.width || 390}`,
      `--screenEmulation.height=${target.height || 844}`,
    );
  }
  if (cookie) {
    args.push(`--extra-headers=${JSON.stringify({ Cookie: cookie })}`);
  }
  const result = spawnSync("npx", ["--yes", ...args], {
    cwd: root,
    encoding: "utf8",
    env: process.env,
  });
  if (result.status !== 0) {
    console.error(result.stderr || result.stdout || `lighthouse failed for ${target.id}`);
    summary.runs.push({ id: target.id, ok: false, error: result.stderr || "failed" });
    continue;
  }
  const report = JSON.parse(await (await import("node:fs/promises")).readFile(outPath, "utf8"));
  const audits = report.audits || {};
  const row = {
    id: target.id,
    ok: true,
    path: target.path,
    form_factor: target.formFactor,
    performance_score: report.categories?.performance?.score ?? null,
    lcp_ms: audits["largest-contentful-paint"]?.numericValue ?? null,
    inp_ms: audits["interaction-to-next-paint"]?.numericValue ?? null,
    cls: audits["cumulative-layout-shift"]?.numericValue ?? null,
    tbt_ms: audits["total-blocking-time"]?.numericValue ?? null,
    transfer_bytes: audits["total-byte-weight"]?.numericValue ?? null,
    artifact: `${stamp}-${target.id}.json`,
  };
  summary.runs.push(row);
  console.log(JSON.stringify(row));
}

const summaryPath = join(outDir, `${stamp}-summary.json`);
await writeFile(summaryPath, `${JSON.stringify(summary, null, 2)}\n`);
console.log(`Wrote ${summaryPath}`);
