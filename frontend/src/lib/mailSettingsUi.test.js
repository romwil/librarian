import assert from "node:assert/strict";
import { test } from "node:test";
import {
  mailSavePayload,
  mailTestResultMessage,
  normalizeMailSettings,
  savedSecretLabel,
} from "./mailSettingsUi.js";

test("savedSecretLabel notes retained secrets", () => {
  assert.equal(savedSecretLabel("Password", false), "Password");
  assert.equal(savedSecretLabel("Password", true), "Password (saved — leave blank to keep)");
});

test("mailTestResultMessage includes recipient", () => {
  assert.match(mailTestResultMessage({ to_email: "a@b.co", provider: "resend" }), /a@b\.co/);
  assert.match(mailTestResultMessage({ to_email: "a@b.co", provider: "resend" }), /resend/);
});

test("normalizeMailSettings defaults and mailSavePayload", () => {
  const empty = normalizeMailSettings(null);
  assert.equal(empty.provider, "off");
  assert.equal(empty.from_name, "Librarian");
  assert.equal(empty.smtp_port, 587);
  assert.equal(empty.smtp_use_tls, true);

  const payload = mailSavePayload({
    ...empty,
    enabled: true,
    provider: "smtp",
    from_email: "hall@example.com",
    smtp_password: "",
  });
  assert.equal(payload.enabled, true);
  assert.equal(payload.smtp_password, "");
  assert.equal(payload.from_email, "hall@example.com");
});
