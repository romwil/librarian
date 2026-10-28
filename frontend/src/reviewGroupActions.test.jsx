// @vitest-environment jsdom
import assert from "node:assert/strict";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it } from "vitest";
import HoldsGroupActions from "./components/HoldsGroupActions.jsx";
import {
  bulkResultSummary,
  deleteGroupConfirmCopy,
  effectiveReviewReason,
  groupHoldSlipsByReason,
  isDuplicateGroup,
  purgePreviewCopy,
  reviewReasonFourWords,
  suggestBatchSummary,
  triageCountsFromWorks,
} from "./review.js";

function group(reason, works, label = "Low confidence") {
  return { reason, label, hint: "", recommendedMotion: "apply", works };
}

const slips = [
  { id: "a", title: "A", review_reason: "low_confidence", folder_path: "/data/complete/a" },
  { id: "b", title: "B", review_reason: "low_confidence", folder_path: "/data/complete/b" },
];

describe("group action helpers", () => {
  it("delete confirm says the download folder stays on disk", () => {
    const copy = deleteGroupConfirmCopy({ count: 3, label: "Low confidence" });
    assert.match(copy.title, /Delete 3 hold slips/);
    assert.match(copy.body, /Wanted request/);
    assert.match(copy.body, /completed-download folder is not deleted/);
    assert.equal(copy.confirmLabel, "Delete 3 slips");
  });

  it("purge preview reports exact vs unassessable before confirm", () => {
    const copy = purgePreviewCopy({
      purgeable: 2,
      unassessable: 1,
      evidence: { exact_fingerprint: 2, unassessable: 1, same_normalized_identity: 4 },
    });
    assert.equal(copy.exact, 2);
    assert.equal(copy.unassessable, 1);
    assert.equal(copy.others, 4);
    assert.equal(copy.confirmLabel, "Purge 2");
    assert.match(copy.lines.join(" "), /never purged on a fuzzy match/);
    assert.equal(purgePreviewCopy({ purgeable: 0, unassessable: 3 }).confirmLabel, "");
  });

  it("only duplicate piles offer purge", () => {
    assert.equal(isDuplicateGroup("collision"), true);
    assert.equal(isDuplicateGroup("possible_duplicate"), true);
    assert.equal(isDuplicateGroup("low_confidence"), false);
  });

  it("bulk summary names partial failures and skip reasons", () => {
    const text = bulkResultSummary({
      action: "delete",
      examined: 4,
      changed: 2,
      skipped: 2,
      failed: 1,
      reasons: { not_in_group: 1, failed: 1 },
      failures: [{ id: "x", title: "Broken", error: "disk said no" }],
    });
    assert.match(text, /Deleted 2 of 4\./);
    assert.match(text, /Skipped 2: 1 not in this group, 1 failed\./);
    assert.match(text, /Download folders stay on disk/);
    assert.match(text, /Broken: disk said no/);
  });

  it("server effective_reason wins over the client guess", () => {
    const work = { review_reason: "low_confidence", effective_reason: "ready_to_file" };
    assert.equal(effectiveReviewReason(work), "ready_to_file");
    const groups = groupHoldSlipsByReason([work, { id: "z", review_reason: "collision" }]);
    assert.deepEqual(
      groups.map((g) => [g.reason, g.label]),
      [
        ["ready_to_file", "Ready to file"],
        ["collision", "Collision"],
      ],
    );
    assert.equal(reviewReasonFourWords("possible_duplicate").split(/\s+/).length, 4);
    assert.equal(reviewReasonFourWords("ready_to_file").split(/\s+/).length, 4);
  });
});

describe("live model triage counts", () => {
  it("reports each server counter as-is and never subtracts applied from sent", () => {
    const line = suggestBatchSummary({
      status: "running",
      done: 3,
      total: 10,
      suggested: 3,
      trusted: 1,
      ambiguous: 1,
      failed: 1,
      applied: 1,
    });
    assert.match(line, /3 of 10/);
    assert.match(line, /1 ready to file/);
    assert.match(line, /1 need a decision/);
    assert.match(line, /1 model unavailable/);
    assert.match(line, /1 filed/);
    assert.doesNotMatch(line, /still need a person/);
    const done = suggestBatchSummary({ status: "completed", suggested: 10, trusted: 6, ambiguous: 3, failed: 1, applied: 6 });
    assert.match(done, /10 sent: 6 ready to file, 3 need a decision, 1 model unavailable, 6 filed/);
  });

  it("desk counts come from persisted slip triage", () => {
    const counts = triageCountsFromWorks([
      { llm_triage: { outcome: "trusted" } },
      { llm_triage: { outcome: "trusted" } },
      { llm_triage: { outcome: "ambiguous" } },
      { llm_triage: { outcome: "failed" } },
      { llm_triage: null },
      {},
    ]);
    assert.deepEqual(counts, { trusted: 2, ambiguous: 1, failed: 1 });
  });
});

describe("HoldsGroupActions", () => {
  it("delete asks first, Escape cancels and returns focus, confirm sends the pile ids", async () => {
    const user = userEvent.setup();
    const calls = [];
    const changed = [];
    const bulk = async (body) => {
      calls.push(body);
      return { action: "delete", examined: 2, changed: 2, skipped: 0, failed: 0, reasons: {} };
    };
    render(<HoldsGroupActions group={group("low_confidence", slips)} bulk={bulk} onChanged={(r) => changed.push(r)} />);
    const actions = screen.getByRole("group", { name: "Low confidence group actions" });
    const trigger = within(actions).getByRole("button", { name: "Delete group (2)" });
    assert.equal(within(actions).queryByRole("button", { name: "Purge duplicate group" }), null);
    assert.equal(within(actions).queryByRole("button", { name: /re-want/i }), null);

    await user.click(trigger);
    const dialog = screen.getByRole("dialog", { name: /Delete 2 hold slips/ });
    assert.match(dialog.textContent, /completed-download folder is not deleted/);
    assert.equal(document.activeElement, within(dialog).getByRole("button", { name: "Cancel" }));
    await user.keyboard("{Escape}");
    assert.equal(screen.queryByRole("dialog"), null);
    assert.equal(document.activeElement, trigger);
    assert.equal(calls.length, 0);

    await user.click(trigger);
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete 2 slips" }));
    await waitFor(() => assert.equal(calls.length, 1));
    assert.deepEqual(calls[0], { reason: "low_confidence", action: "delete", workIds: ["a", "b"], dryRun: false });
    assert.equal(changed.length, 1);
    assert.match(screen.getByRole("status").textContent, /Deleted 2 of 2/);
  });

  it("purge previews evidence before the owner confirms", async () => {
    const user = userEvent.setup();
    const calls = [];
    const bulk = async (body) => {
      calls.push(body);
      if (body.dryRun) {
        return { dry_run: true, purgeable: 1, unassessable: 2, evidence: { exact_fingerprint: 1, unassessable: 2 } };
      }
      return { action: "purge_duplicates", examined: 3, changed: 1, skipped: 2, failed: 0, reasons: { unassessable: 2 } };
    };
    render(<HoldsGroupActions group={group("collision", slips, "Collision")} bulk={bulk} />);
    await user.click(screen.getByRole("button", { name: "Purge duplicate group" }));
    const dialog = await screen.findByRole("dialog", { name: "Purge 1 exact duplicate?" });
    assert.match(dialog.textContent, /1 exact fingerprint/);
    assert.match(dialog.textContent, /2 unassessable/);
    assert.match(screen.getByTestId("holds-group-evidence").textContent, /1 exact fingerprint · 2 unassessable/);
    assert.equal(calls.length, 1);
    assert.equal(calls[0].dryRun, true);
    await user.click(within(dialog).getByRole("button", { name: "Purge 1" }));
    await waitFor(() => assert.equal(calls.length, 2));
    assert.equal(calls[1].dryRun, false);
    assert.match(screen.getByRole("status").textContent, /Purged 1 of 3\. Skipped 2: 2 unassessable/);
  });

  it("shows a partial failure as an alert, not a success", async () => {
    const user = userEvent.setup();
    const bulk = async () => ({
      action: "delete",
      examined: 2,
      changed: 1,
      skipped: 1,
      failed: 1,
      reasons: { failed: 1 },
      failures: [{ id: "b", title: "B", error: "disk said no" }],
    });
    render(<HoldsGroupActions group={group("low_confidence", slips)} bulk={bulk} />);
    await user.click(screen.getByRole("button", { name: "Delete group (2)" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete 2 slips" }));
    const status = await screen.findByRole("status");
    assert.match(status.textContent, /Deleted 1 of 2.*1 failed.*B: disk said no/);
    assert.ok(status.classList.contains("alert"));
  });

  it("a rejected request leaves the slips and reports the error", async () => {
    const user = userEvent.setup();
    const bulk = async () => {
      throw new Error("Server down");
    };
    render(<HoldsGroupActions group={group("low_confidence", slips)} bulk={bulk} />);
    await act(async () => {
      await user.click(screen.getByRole("button", { name: "Delete group (2)" }));
    });
    await user.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete 2 slips" }));
    const status = await screen.findByRole("status");
    assert.ok(status.classList.contains("alert"));
    assert.ok(status.textContent.length > 0);
  });
});
