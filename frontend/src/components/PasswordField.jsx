import { useState } from "react";
import { FieldLabel } from "./FieldHelp.jsx";
import { HIDE_PASSWORD, SHOW_PASSWORD } from "../copy.js";

export default function PasswordField({
  id,
  label,
  help,
  value,
  onChange,
  autoComplete = "current-password",
  minLength = 8,
  required = true,
}) {
  const [visible, setVisible] = useState(false);
  const toggleLabel = visible ? HIDE_PASSWORD : SHOW_PASSWORD;
  return (
    <div className="field">
      <FieldLabel htmlFor={id} label={label} help={help} />
      <div className="password-field">
        <input
          id={id}
          type={visible ? "text" : "password"}
          value={value}
          onChange={onChange}
          autoComplete={autoComplete}
          minLength={minLength}
          required={required}
        />
        <button
          type="button"
          className="cta ghost password-toggle"
          aria-pressed={visible}
          aria-controls={id}
          onClick={() => setVisible((open) => !open)}
        >
          {toggleLabel}
        </button>
      </div>
    </div>
  );
}
