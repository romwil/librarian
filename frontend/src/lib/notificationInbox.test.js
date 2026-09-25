import assert from "node:assert/strict";
import test from "node:test";
import {
  formatUnreadBadge,
  inboxCardCopy,
  inboxHeadline,
  inboxItemHref,
  normalizeChannels,
  normalizeTiming,
} from "./notificationInbox.js";

test("formatUnreadBadge caps at 99+", () => {
  assert.equal(formatUnreadBadge(0), "");
  assert.equal(formatUnreadBadge(3), "3");
  assert.equal(formatUnreadBadge(100), "99+");
});

test("inboxHeadline uses Librarian voice for kinds", () => {
  assert.equal(inboxHeadline([]), "Inbox");
  assert.equal(inboxHeadline([{ kind: "arrived" }]), "Something arrived for you");
  assert.equal(inboxHeadline([{ kind: "needs_you" }, { kind: "arrived" }]), "2 new notices");
});

test("inboxCardCopy and href for Review and Maintain", () => {
  const needs = inboxCardCopy({ kind: "needs_you", title: "Three slips waiting", body: "Clear or repair." });
  assert.equal(needs.eyebrow, "Needs you");
  assert.equal(needs.lead, "Three slips waiting");
  assert.equal(inboxItemHref({ kind: "needs_you" }), "/review");
  assert.equal(inboxItemHref({ kind: "shelf_health" }), "/maintain");
  assert.equal(
    inboxItemHref({ kind: "arrived", payload: { work_id: "abc" } }),
    "/works/abc",
  );
});

test("normalizeTiming and channels reject junk", () => {
  assert.equal(normalizeTiming("WEEKLY"), "weekly");
  assert.equal(normalizeTiming("nope"), "realtime");
  assert.deepEqual(normalizeChannels(["email", "inbox", "pager"]), ["email", "inbox"]);
  assert.deepEqual(normalizeChannels([]), ["inbox"]);
});

test("hostile title does not break card copy", () => {
  const card = inboxCardCopy({
    kind: "someone_finished",
    title: "<script>alert(1)</script>",
    body: "x".repeat(5000),
  });
  assert.equal(card.lead.includes("<script>"), true);
  assert.equal(card.note.length, 5000);
});
