import { useEffect, useRef } from "react";

const FOCUSABLE = [
  "a[href]",
  "button:not([disabled])",
  "textarea:not([disabled])",
  "input:not([disabled]):not([type='hidden'])",
  "select:not([disabled])",
  "[tabindex]:not([tabindex='-1'])",
].join(",");

/** Focusable controls inside an overlay, skipping hidden and disabled nodes. */
export function getFocusable(root) {
  if (!root || typeof root.querySelectorAll !== "function") return [];
  return [...root.querySelectorAll(FOCUSABLE)].filter((node) => {
    if (node.hasAttribute("disabled")) return false;
    if (node.getAttribute("aria-hidden") === "true") return false;
    if (node.closest("[aria-hidden='true']") && node.closest("[aria-hidden='true']") !== root) return false;
    const style = typeof window !== "undefined" ? window.getComputedStyle(node) : null;
    if (style && (style.visibility === "hidden" || style.display === "none")) return false;
    return true;
  });
}

/**
 * Move focus into an overlay, trap Tab, dismiss on Escape, restore the opener.
 * Call with `open` false to no-op; the overlay may unmount after the flag drops.
 */
export default function useModal({
  open,
  onEscape,
  panelRef,
  initialFocusRef = null,
  returnFocusRef = null,
} = {}) {
  const onEscapeRef = useRef(onEscape);
  onEscapeRef.current = onEscape;
  const restoreRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    restoreRef.current = returnFocusRef?.current || document.activeElement;

    const panel = panelRef?.current;
    const initial =
      initialFocusRef?.current ||
      panel?.querySelector("h2") ||
      getFocusable(panel)[0] ||
      panel;
    if (initial && typeof initial.focus === "function") {
      initial.focus();
    }

    function onKey(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        onEscapeRef.current?.();
        return;
      }
      if (event.key !== "Tab") return;
      const root = panelRef?.current;
      if (!root) return;
      const focusable = getFocusable(root);
      if (!focusable.length) {
        event.preventDefault();
        root.focus?.();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (event.shiftKey && (active === first || !root.contains(active))) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && (active === last || !root.contains(active))) {
        event.preventDefault();
        first.focus();
      }
    }

    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("keydown", onKey);
      const opener = restoreRef.current;
      if (opener && typeof opener.focus === "function") opener.focus();
    };
  }, [open, panelRef, initialFocusRef, returnFocusRef]);
}
