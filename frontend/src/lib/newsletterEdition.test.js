/**
 * Pure helpers for owner library-letter push UI (unit coverage twin of notificationInbox).
 */
import assert from "node:assert/strict";
import test from "node:test";
import {
  NEWSLETTER_SCOPES,
  NEWSLETTER_TIMINGS,
  newsletterConfirmMessage,
  newsletterResultMessage,
  normalizeNewsletterTiming,
} from "./notificationInbox.js";

test("newsletter scopes and timings are stable", () => {
  assert.deepEqual(
    NEWSLETTER_SCOPES.map((row) => row.value),
    ["self", "all"],
  );
  assert.deepEqual(
    NEWSLETTER_TIMINGS.map((row) => row.value),
    ["weekly", "monthly"],
  );
  assert.equal(normalizeNewsletterTiming("month"), "weekly"); // only monthly|weekly tokens
  assert.equal(normalizeNewsletterTiming("monthly"), "monthly");
});

test("confirm and result messages stay household voice", () => {
  assert.match(newsletterConfirmMessage("all"), /opted in/i);
  assert.doesNotMatch(newsletterConfirmMessage("self"), /force-email/i);
  const msg = newsletterResultMessage({ delivered: 0, emailed: 0, skipped_opt_out: 3, skipped_not_due: 1 });
  assert.match(msg, /not opted in/);
  assert.match(msg, /not due yet/);
});
