import { useEffect, useId, useRef, useState } from "react";

export default function FieldHelp({ label, children }) {
  const [open, setOpen] = useState(false);
  const tipId = useId();
  const root = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    function onKey(event) {
      if (event.key === "Escape") setOpen(false);
    }
    function onPointer(event) {
      if (!root.current?.contains(event.target)) setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    window.addEventListener("pointerdown", onPointer);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("pointerdown", onPointer);
    };
  }, [open]);

  if (!children) return null;

  return (
    <span className="field-help" ref={root}>
      <button
        type="button"
        className="help-q"
        aria-label={`About ${label}`}
        aria-expanded={open}
        aria-controls={tipId}
        onClick={() => setOpen((value) => !value)}
      >
        ?
      </button>
      {open ? (
        <span id={tipId} role="tooltip" className="help-tip">
          {children}
        </span>
      ) : null}
    </span>
  );
}

export function FieldLabel({ htmlFor, label, help }) {
  return (
    <span className="field-label">
      <label htmlFor={htmlFor}>{label}</label>
      <FieldHelp label={label}>{help}</FieldHelp>
    </span>
  );
}
