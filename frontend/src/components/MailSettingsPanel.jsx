import { useState } from "react";
import { FieldLabel } from "./FieldHelp.jsx";
import { api } from "../api.js";
import {
  mailSavePayload,
  mailTestResultMessage,
  normalizeMailSettings,
  savedSecretLabel,
} from "../lib/mailSettingsUi.js";
import { humanError } from "../copy.js";

const PROVIDERS = [
  { value: "off", label: "Off" },
  { value: "smtp", label: "SMTP" },
  { value: "resend", label: "Resend" },
];

/**
 * Owner Settings → Mail install panel (SMTP / Resend + test send).
 * Nested under settings.mail; blank secrets keep the prior value on Save.
 */
export default function MailSettingsPanel({ settings, onChange }) {
  const mail = normalizeMailSettings(settings?.mail);
  const [testTo, setTestTo] = useState("");
  const [testStatus, setTestStatus] = useState("");
  const [testing, setTesting] = useState(false);

  function patchMail(partial) {
    onChange({
      ...settings,
      mail: { ...mail, ...partial },
    });
  }

  async function handleTest() {
    setTesting(true);
    setTestStatus("");
    try {
      const result = await api.testMail({ to_email: testTo.trim() });
      setTestStatus(mailTestResultMessage(result));
    } catch (err) {
      setTestStatus(humanError(err));
    } finally {
      setTesting(false);
    }
  }

  const transportOpen = Boolean(mail.enabled) || (mail.provider && mail.provider !== "off");

  return (
    <section className="settings-panel" id="mail" data-testid="settings-panel-mail" aria-labelledby="settings-mail-heading">
      <p className="kicker" id="settings-mail-heading">
        Mail
      </p>
      <h2>Outbound email</h2>
      <p className="lede">
        SMTP or Resend for household notices once notifications land. Leave password and API key blank on save to keep
        what is already stored. Secrets stay in settings.json / env — never in the repo.
      </p>

      <div className="field field-check">
        <label htmlFor="setting-mail-enabled">
          <input
            id="setting-mail-enabled"
            type="checkbox"
            checked={Boolean(mail.enabled)}
            onChange={(e) => patchMail({ enabled: e.target.checked })}
            data-testid="mail-enabled"
          />
          Enable outbound mail
        </label>
      </div>

      <div className="field">
        <FieldLabel htmlFor="setting-mail-provider" label="Provider" />
        <select
          id="setting-mail-provider"
          value={mail.provider || "off"}
          onChange={(e) => patchMail({ provider: e.target.value })}
          data-testid="mail-provider"
        >
          {PROVIDERS.map((row) => (
            <option key={row.value} value={row.value}>
              {row.label}
            </option>
          ))}
        </select>
      </div>

      {transportOpen ? (
        <>
          <div className="field">
            <FieldLabel htmlFor="setting-mail-from-email" label="From email" />
            <input
              id="setting-mail-from-email"
              type="email"
              value={mail.from_email || ""}
              onChange={(e) => patchMail({ from_email: e.target.value })}
              placeholder="alerts@example.com"
              data-testid="mail-from-email"
            />
          </div>
          <div className="field">
            <FieldLabel htmlFor="setting-mail-from-name" label="From name" />
            <input
              id="setting-mail-from-name"
              type="text"
              value={mail.from_name || ""}
              onChange={(e) => patchMail({ from_name: e.target.value })}
              placeholder="Librarian"
              data-testid="mail-from-name"
            />
          </div>
        </>
      ) : null}

      {mail.provider === "smtp" ? (
        <div className="settings-subsection" data-testid="mail-smtp-section">
          <h3 className="kicker">SMTP</h3>
          <div className="field">
            <FieldLabel htmlFor="setting-mail-smtp-host" label="Host" />
            <input
              id="setting-mail-smtp-host"
              type="text"
              value={mail.smtp_host || ""}
              onChange={(e) => patchMail({ smtp_host: e.target.value })}
              placeholder="smtp.example.com"
              data-testid="mail-smtp-host"
              spellCheck={false}
            />
          </div>
          <div className="field">
            <FieldLabel htmlFor="setting-mail-smtp-port" label="Port" />
            <input
              id="setting-mail-smtp-port"
              type="number"
              value={mail.smtp_port ?? 587}
              onChange={(e) => patchMail({ smtp_port: Number(e.target.value) || 587 })}
              data-testid="mail-smtp-port"
            />
          </div>
          <div className="field">
            <FieldLabel htmlFor="setting-mail-smtp-username" label="Username" />
            <input
              id="setting-mail-smtp-username"
              type="text"
              value={mail.smtp_username || ""}
              onChange={(e) => patchMail({ smtp_username: e.target.value })}
              data-testid="mail-smtp-username"
              autoComplete="off"
            />
          </div>
          <div className="field">
            <FieldLabel
              htmlFor="setting-mail-smtp-password"
              label={savedSecretLabel("Password", Boolean(mail.smtp_password_set))}
            />
            <input
              id="setting-mail-smtp-password"
              type="password"
              value={mail.smtp_password || ""}
              onChange={(e) => patchMail({ smtp_password: e.target.value })}
              data-testid="mail-smtp-password"
              autoComplete="new-password"
              placeholder={mail.smtp_password_set ? "••••••••" : ""}
            />
          </div>
          <div className="field field-check">
            <label htmlFor="setting-mail-smtp-tls">
              <input
                id="setting-mail-smtp-tls"
                type="checkbox"
                checked={mail.smtp_use_tls !== false}
                onChange={(e) => patchMail({ smtp_use_tls: e.target.checked })}
                data-testid="mail-smtp-tls"
              />
              Use STARTTLS
            </label>
          </div>
        </div>
      ) : null}

      {mail.provider === "resend" ? (
        <div className="settings-subsection" data-testid="mail-resend-section">
          <h3 className="kicker">Resend</h3>
          <div className="field">
            <FieldLabel
              htmlFor="setting-mail-resend-key"
              label={savedSecretLabel("API key", Boolean(mail.resend_api_key_set))}
            />
            <input
              id="setting-mail-resend-key"
              type="password"
              value={mail.resend_api_key || ""}
              onChange={(e) => patchMail({ resend_api_key: e.target.value })}
              data-testid="mail-resend-api-key"
              autoComplete="new-password"
              placeholder={mail.resend_api_key_set ? "••••••••" : "re_…"}
            />
          </div>
        </div>
      ) : null}

      <details className="settings-advanced">
        <summary>Email template</summary>
        <div className="field">
          <FieldLabel htmlFor="setting-mail-subject-prefix" label="Subject prefix" />
          <input
            id="setting-mail-subject-prefix"
            type="text"
            value={mail.subject_prefix || ""}
            onChange={(e) => patchMail({ subject_prefix: e.target.value })}
            placeholder="[Librarian]"
            data-testid="mail-subject-prefix"
          />
        </div>
        <div className="field">
          <FieldLabel htmlFor="setting-mail-footer" label="Footer text" />
          <textarea
            id="setting-mail-footer"
            rows={3}
            value={mail.footer_text || ""}
            onChange={(e) => patchMail({ footer_text: e.target.value })}
            data-testid="mail-footer-text"
          />
        </div>
        <div className="field">
          <FieldLabel htmlFor="setting-mail-logo" label="Logo URL" />
          <input
            id="setting-mail-logo"
            type="url"
            value={mail.logo_url || ""}
            onChange={(e) => patchMail({ logo_url: e.target.value })}
            data-testid="mail-logo-url"
            placeholder="https://…"
          />
        </div>
      </details>

      <div className="settings-subsection" data-testid="mail-test-section">
        <h3 className="kicker">Send a test</h3>
        <div className="field">
          <FieldLabel htmlFor="setting-mail-test-to" label="Send test to" />
          <input
            id="setting-mail-test-to"
            type="email"
            value={testTo}
            onChange={(e) => setTestTo(e.target.value)}
            placeholder="you@example.com"
            data-testid="mail-test-to"
          />
        </div>
        <div className="cta-row">
          <button
            type="button"
            className="cta ghost"
            onClick={handleTest}
            disabled={testing || !testTo.trim()}
            data-testid="mail-test-send"
          >
            {testing ? "Sending…" : "Send test email"}
          </button>
        </div>
        {testStatus ? (
          <p className="muted" role="status" data-testid="mail-test-status">
            {testStatus}
          </p>
        ) : null}
      </div>

      <p className="muted" data-testid="mail-save-hint">
        Use Save below to persist mail settings ({mailSavePayload(mail).provider}).
      </p>
    </section>
  );
}
