#!/usr/bin/env node
/**
 * Cross-platform E2E server launcher (Playwright webServer).
 * Default port 8794 — not product 8793, not Automat 8788/8790/8791/8792,
 * and not Projectionist's e2e default 8799.
 */
import { spawn, spawnSync } from "node:child_process";
import { existsSync, mkdtempSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PORT = process.env.E2E_PORT || "8794";
const DATA_DIR =
  process.env.E2E_DATA_DIR || mkdtempSync(path.join(os.tmpdir(), "librarian-e2e-"));

function resolvePython(root) {
  const candidates = [
    path.join(root, ".venv", "Scripts", "python.exe"),
    path.join(root, ".venv", "bin", "python"),
  ];
  for (const candidate of candidates) {
    if (existsSync(candidate)) return candidate;
  }
  return process.platform === "win32" ? "python" : "python3";
}

function npm(args, cwd) {
  const cmd = process.platform === "win32" ? "npm.cmd" : "npm";
  const result = spawnSync(cmd, args, {
    cwd,
    stdio: "inherit",
    shell: process.platform === "win32",
  });
  if (result.status !== 0) {
    process.exit(result.status ?? 1);
  }
}

const distDir = path.join(ROOT, "frontend", "dist");
if (!existsSync(distDir)) {
  console.log("Building frontend for E2E...");
  const frontendDir = path.join(ROOT, "frontend");
  npm(["install"], frontendDir);
  npm(["run", "build"], frontendDir);
}

const python = resolvePython(ROOT);
const env = {
  ...process.env,
  DATA_DIR,
  PORT,
  // Throwaway e2e-only credentials — not household secrets.
  LIBRARIAN_OWNER_USERNAME: process.env.LIBRARIAN_OWNER_USERNAME || "e2e-owner",
  LIBRARIAN_OWNER_PASSWORD: process.env.LIBRARIAN_OWNER_PASSWORD || "e2e-password-ok",
  LIBRARIAN_SESSION_SECRET:
    process.env.LIBRARIAN_SESSION_SECRET || "e2e-session-secret-value-not-dev",
};

console.log(`Starting Librarian E2E server on :${PORT} (DATA_DIR=${DATA_DIR})`);

const child = spawn(python, ["-m", "librarian.web"], {
  cwd: ROOT,
  env,
  stdio: "inherit",
});

child.on("error", (err) => {
  console.error(err);
  process.exit(1);
});

child.on("exit", (code, signal) => {
  if (signal) {
    process.kill(process.pid, signal);
  }
  process.exit(code ?? 1);
});
