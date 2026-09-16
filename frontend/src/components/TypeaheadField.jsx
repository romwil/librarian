import { useEffect, useId, useRef, useState } from "react";
import { api } from "../api.js";

const DEBOUNCE_MS = 180;
const TYPEAHEAD_FIELDS = new Set(["author", "title", "series", "artist", "album", "year"]);

export function isTypeaheadField(field) {
  return TYPEAHEAD_FIELDS.has(field);
}

export default function TypeaheadField({
  id,
  field,
  kind = "",
  value = "",
  onChange,
  className,
  onEnterSubmit,
}) {
  const listId = useId();
  const wrapRef = useRef(null);
  const abortRef = useRef(null);
  const timerRef = useRef(null);
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [active, setActive] = useState(-1);

  useEffect(() => {
    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      abortRef.current?.abort();
    };
  }, []);

  useEffect(() => {
    function onDocPointer(event) {
      if (!wrapRef.current?.contains(event.target)) {
        setOpen(false);
        setActive(-1);
      }
    }
    document.addEventListener("pointerdown", onDocPointer);
    return () => document.removeEventListener("pointerdown", onDocPointer);
  }, []);

  function fetchSuggestions(query) {
    if (timerRef.current) clearTimeout(timerRef.current);
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    timerRef.current = setTimeout(async () => {
      try {
        const data = await api.suggest({ field, kind, q: query, limit: 12, signal: controller.signal });
        if (controller.signal.aborted) return;
        const next = Array.isArray(data?.items) ? data.items : [];
        setItems(next);
        setOpen(next.length > 0);
        setActive(next.length ? 0 : -1);
      } catch (err) {
        if (err?.name === "AbortError" || controller.signal.aborted) return;
        setItems([]);
        setOpen(false);
        setActive(-1);
      }
    }, DEBOUNCE_MS);
  }

  function pick(item) {
    const next = item?.value ?? "";
    onChange(next);
    setOpen(false);
    setActive(-1);
    setItems([]);
  }

  return (
    <div className="typeahead" ref={wrapRef}>
      <input
        id={id}
        className={className}
        role="combobox"
        aria-autocomplete="list"
        aria-expanded={open}
        aria-controls={listId}
        aria-activedescendant={active >= 0 ? `${listId}-${active}` : undefined}
        autoComplete="off"
        value={value}
        onChange={(event) => {
          const next = event.target.value;
          onChange(next);
          fetchSuggestions(next);
        }}
        onFocus={() => {
          // Empty q still returns a short catalog head (years include decades).
          fetchSuggestions(value);
        }}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            if (!open && items.length) setOpen(true);
            if (!items.length) {
              fetchSuggestions(value);
              return;
            }
            event.preventDefault();
            setOpen(true);
            setActive((prev) => (prev + 1) % items.length);
            return;
          }
          if (event.key === "ArrowUp") {
            if (!items.length) return;
            event.preventDefault();
            setOpen(true);
            setActive((prev) => (prev <= 0 ? items.length - 1 : prev - 1));
            return;
          }
          if (event.key === "Escape") {
            if (open) {
              event.preventDefault();
              setOpen(false);
              setActive(-1);
            }
            return;
          }
          if (event.key === "Enter") {
            if (open && active >= 0 && items[active]) {
              event.preventDefault();
              pick(items[active]);
              return;
            }
            event.preventDefault();
            onEnterSubmit?.();
          }
        }}
      />
      {open && items.length ? (
        <ul id={listId} className="typeahead-menu" role="listbox">
          {items.map((item, index) => (
            <li
              key={`${item.value}-${index}`}
              id={`${listId}-${index}`}
              role="option"
              aria-selected={index === active}
              className={`typeahead-option${index === active ? " is-active" : ""}`}
              onMouseEnter={() => setActive(index)}
              onMouseDown={(event) => {
                event.preventDefault();
                pick(item);
              }}
            >
              <span className="typeahead-value">{item.value}</span>
              {item.meta === "catalog" ? <span className="typeahead-meta">shelf</span> : null}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
