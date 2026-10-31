import assert from "node:assert/strict";
import { test } from "vitest";
import { backupSummary } from "./lib/backupStatus.js";

test("backupSummary is null when the server sends no backup blob", () => {
  assert.equal(backupSummary({}), null);
  assert.equal(backupSummary(null), null);
});

test("backupSummary says No backup yet before the first snapshot", () => {
  const summary = backupSummary({ backup: { last_backup: null, daily_count: 0, weekly_count: 0 } });
  assert.equal(summary.line, "No backup yet");
  assert.equal(summary.error, "");
});

test("backupSummary names the last backup and what is kept", () => {
  const summary = backupSummary({
    backup: {
      last_backup: "2026-10-30T03:10:00-04:00",
      daily_count: 7,
      weekly_count: 1,
      last_error: null,
    },
  });
  assert.match(summary.line, /^Last backup .+ · 7 dailies, 1 weekly kept$/);
});

test("backupSummary surfaces a failed run", () => {
  const summary = backupSummary({
    backup: { last_backup: null, last_error: "  Backup failed integrity_check: bad page  " },
  });
  assert.equal(summary.line, "No backup yet");
  assert.equal(summary.error, "Backup failed integrity_check: bad page");
});
