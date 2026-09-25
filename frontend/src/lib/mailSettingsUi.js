/** Pure copy/helpers for Owner Settings → Mail. */

/**
 * Field label that notes a secret is already stored.
 * @param {string} label
 * @param {boolean} isSet
 * @returns {string}
 */
export function savedSecretLabel(label, isSet) {
  return isSet ? `${label} (saved — leave blank to keep)` : label;
}

/**
 * Short success line after mail test.
 * @param {{ to_email?: string, provider?: string }} result
 * @returns {string}
 */
export function mailTestResultMessage(result = {}) {
  const to = result.to_email || "the address you entered";
  const provider = result.provider ? ` via ${result.provider}` : "";
  return `Test email sent to ${to}${provider}.`;
}

/**
 * Normalize mail blob from settings for form state.
 * @param {Record<string, unknown>|null|undefined} mail
 */
export function normalizeMailSettings(mail) {
  const row = mail && typeof mail === "object" ? mail : {};
  return {
    enabled: Boolean(row.enabled),
    provider: String(row.provider || "off"),
    from_email: String(row.from_email || ""),
    from_name: String(row.from_name || "Librarian"),
    smtp_host: String(row.smtp_host || ""),
    smtp_port: Number(row.smtp_port) || 587,
    smtp_username: String(row.smtp_username || ""),
    smtp_password: String(row.smtp_password || ""),
    smtp_use_tls: row.smtp_use_tls !== false,
    resend_api_key: String(row.resend_api_key || ""),
    subject_prefix: String(row.subject_prefix || "[Librarian]"),
    footer_text: String(row.footer_text || ""),
    logo_url: String(row.logo_url || ""),
    smtp_password_set: Boolean(row.smtp_password_set),
    resend_api_key_set: Boolean(row.resend_api_key_set),
    configured: Boolean(row.configured),
  };
}

/**
 * Payload for PUT /api/settings mail (omit blank secrets so retain-on-empty works).
 * @param {ReturnType<typeof normalizeMailSettings>} mail
 */
export function mailSavePayload(mail) {
  return {
    enabled: Boolean(mail.enabled),
    provider: mail.provider || "off",
    from_email: mail.from_email || "",
    from_name: mail.from_name || "Librarian",
    smtp_host: mail.smtp_host || "",
    smtp_port: Number(mail.smtp_port) || 587,
    smtp_username: mail.smtp_username || "",
    smtp_password: mail.smtp_password || "",
    smtp_use_tls: mail.smtp_use_tls !== false,
    resend_api_key: mail.resend_api_key || "",
    subject_prefix: mail.subject_prefix || "",
    footer_text: mail.footer_text || "",
    logo_url: mail.logo_url || "",
  };
}
