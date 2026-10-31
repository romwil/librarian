import { FieldLabel } from "./FieldHelp.jsx";

/** Label + control + optional error, wired with `aria-describedby` / `aria-invalid`. */
export default function Field({
  id,
  label,
  help,
  error = "",
  children,
  ...inputProps
}) {
  const errorId = error ? `${id}-error` : undefined;
  return (
    <div className="field">
      <FieldLabel htmlFor={id} label={label} help={help} />
      {children || (
        <input
          id={id}
          aria-invalid={error ? "true" : undefined}
          aria-describedby={errorId}
          {...inputProps}
        />
      )}
      {error ? (
        <p id={errorId} className="field-error">
          {error}
        </p>
      ) : null}
    </div>
  );
}
