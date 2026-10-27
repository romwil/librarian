import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

/**
 * Shared popover/menu behavior: open state, dismiss-on-outside-click and/or
 * Escape, and optional portal placement (getBoundingClientRect against an
 * anchor, re-run on resize/scroll). One hook backs the cover action grip
 * (portaled, anchored to the grip) and the stacks command-bar popovers
 * (genre/author/series, columns, export — no portal, plain absolute CSS).
 *
 * @param {Object} [options]
 * @param {boolean} [options.open] Controlled open state. When provided the hook
 *   does not own the state; dismissals call `onOpenChange(false)`.
 * @param {(next: boolean) => void} [options.onOpenChange] Called with the next
 *   open value whenever the hook requests a change (controlled or uncontrolled).
 * @param {boolean} [options.initialOpen=false] Initial open for uncontrolled use.
 * @param {boolean} [options.closeOnOutside=true] Dismiss when a pointer event
 *   lands outside both the root and popover refs.
 * @param {string} [options.outsideEvent="mousedown"] Event used for outside dismiss.
 * @param {boolean} [options.closeOnEscape=false] Dismiss on the Escape key.
 * @param {string} [options.anchorSelector] Selector queried inside `rootRef` for
 *   the placement anchor; falls back to `rootRef` itself.
 * @param {(anchor: DOMRect, popover: DOMRect, anchorEl: Element) => Object} [options.placement]
 *   Returns the popover style object. Omit for menus that don't portal/position
 *   (plain CSS-absolute popovers skip this). The third argument is the anchor
 *   element so a peek can line the menu up with the sheet.
 * @param {string|number} [options.repositionKey] Extra dependency: when it
 *   changes while open, placement recomputes.
 */
export function useAnchoredPopover({
  open: controlledOpen,
  onOpenChange,
  initialOpen = false,
  closeOnOutside = true,
  outsideEvent = "mousedown",
  closeOnEscape = false,
  anchorSelector,
  placement,
  repositionKey,
} = {}) {
  const controlled = controlledOpen !== undefined;
  const [internalOpen, setInternalOpen] = useState(initialOpen);
  const open = controlled ? controlledOpen : internalOpen;

  const rootRef = useRef(null);
  const popoverRef = useRef(null);
  const [popoverStyle, setPopoverStyle] = useState(null);

  const setOpen = useCallback(
    (value) => {
      const next = typeof value === "function" ? value(open) : value;
      if (!controlled) setInternalOpen(next);
      onOpenChange?.(next);
    },
    [open, controlled, onOpenChange],
  );

  const close = useCallback(() => setOpen(false), [setOpen]);

  useEffect(() => {
    if (!open) return undefined;
    const handleOutside = (event) => {
      const target = event.target;
      if (rootRef.current?.contains(target)) return;
      if (popoverRef.current?.contains(target)) return;
      setOpen(false);
    };
    const handleKey = (event) => {
      if (event.key === "Escape") setOpen(false);
    };
    if (closeOnOutside) document.addEventListener(outsideEvent, handleOutside);
    if (closeOnEscape) document.addEventListener("keydown", handleKey);
    return () => {
      if (closeOnOutside) document.removeEventListener(outsideEvent, handleOutside);
      if (closeOnEscape) document.removeEventListener("keydown", handleKey);
    };
  }, [open, closeOnOutside, outsideEvent, closeOnEscape, setOpen]);

  useLayoutEffect(() => {
    if (!open || !placement) return undefined;
    const position = () => {
      const anchorEl = anchorSelector ? rootRef.current?.querySelector(anchorSelector) : rootRef.current;
      const anchor = anchorEl?.getBoundingClientRect();
      const menu = popoverRef.current?.getBoundingClientRect();
      if (!anchor || !menu) return;
      setPopoverStyle(placement(anchor, menu, anchorEl));
    };
    position();
    window.addEventListener("resize", position);
    window.addEventListener("scroll", position, true);
    return () => {
      window.removeEventListener("resize", position);
      window.removeEventListener("scroll", position, true);
    };
    // `repositionKey` is an intentional trigger to recompute placement when the
    // popover's contents resize (e.g. a submenu opening).
  }, [open, placement, anchorSelector, repositionKey]);

  return { open, setOpen, close, rootRef, popoverRef, popoverStyle };
}
