import assert from "node:assert/strict";
import { describe, it } from "vitest";
import {
  DEFAULT_QUEUE_VIEW,
  bulkDismissConfirmCopy,
  dismissibleQueueJobs,
  emptyQueueViewCopy,
  isQueueBulkDismissible,
  normalizeQueueView,
  queueCounts,
  queueViewLabel,
} from "./queueDesk.js";
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));

describe("queue desk views (PRD-011)", () => {
  it("defaults Downloads to Needs decision / actionable", () => {
    assert.equal(DEFAULT_QUEUE_VIEW, "actionable");
    assert.equal(normalizeQueueView(""), "actionable");
    assert.equal(normalizeQueueView("bogus"), "actionable");
    assert.equal(queueViewLabel("actionable"), "Needs decision");
  });

  it("names Active, History, and All jobs escape hatch", () => {
    assert.equal(queueViewLabel("active"), "Active");
    assert.equal(queueViewLabel("history"), "History");
    assert.equal(queueViewLabel("all"), "All jobs");
  });

  it("empty copy is view-aware", () => {
    assert.match(emptyQueueViewCopy("actionable"), /Nothing needs a decision/i);
    assert.match(emptyQueueViewCopy("active"), /Nothing on the way/i);
    assert.match(emptyQueueViewCopy("history"), /No arrived/i);
  });

  it("bulk dismiss only targets Arrived/Failed — never Asked, active, or Needs you", () => {
    const jobs = [
      { id: "1", status: "asked" },
      { id: "2", status: "failed" },
      { id: "3", status: "organized" },
      { id: "4", status: "review" },
      { id: "5", status: "downloading" },
      { id: "6", status: "skipped" },
    ];
    const dismissed = dismissibleQueueJobs(jobs);
    assert.deepEqual(
      dismissed.map((j) => j.status).sort(),
      ["failed", "organized", "skipped"],
    );
    assert.equal(isQueueBulkDismissible({ status: "asked" }), false);
    assert.equal(isQueueBulkDismissible({ status: "review" }), false);
    assert.equal(isQueueBulkDismissible({ status: "queued" }), false);
  });

  it("bulk dismiss confirm names count and undo reminder", () => {
    const copy = bulkDismissConfirmCopy([
      { id: "a", status: "organized" },
      { id: "b", status: "failed" },
    ]);
    assert.match(copy.title, /Dismiss 2 jobs/);
    assert.match(copy.body, /2 Arrived \/ Failed/);
    assert.match(copy.confirmLabel, /Dismiss 2/);
    assert.match(copy.undoReminder, /no Safe undo/i);
  });

  it("normalizes count chips", () => {
    assert.deepEqual(queueCounts({ actionable: 3, active: "2", history: null }), {
      actionable: 3,
      active: 2,
      history: 0,
      all: 0,
    });
  });
});

describe("purge shells confirm (UX-005)", () => {
  it("Maintain purge dialog shows count copy and undo reminder", () => {
    const maintainSrc = readFileSync(join(root, "pages/MaintainPage.jsx"), "utf8");
    assert.match(maintainSrc, /maintain-purge-shells-count-copy/);
    assert.match(maintainSrc, /maintain-purge-shells-undo/);
    assert.match(maintainSrc, /Safe undo can restore purged shells/);
    assert.match(maintainSrc, /This removes \{Number\(purgePreview\?\.would_purge/);
  });
});
