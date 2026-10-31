import { createPortal } from "react-dom";
import { useAnchoredPopover } from "../hooks/useAnchoredPopover.js";
import { placeActionMenu } from "../lib/workActionMenu.js";

/**
 * ⋮ grip + portaled action menu for a title cover (work hero, peek, rail
 * CoverCard). One primary action (Read / Listen / Ask the house) stays
 * outside this component as an ordinary `.cta` — see `lib/workActionMenu.js`
 * for the primary-vs-secondary split. Everything else renders as `children`
 * inside the portaled popover.
 *
 * Portaled to `document.body` so a rail's overflow can't clip the menu, and
 * closes on Escape, outside click, or any link/button activated inside it.
 * The grip stops the click so a cover button underneath does not open.
 */

export default function WorkActionMenu({ label = "", onOpen, children, className = "", testId = "work-action" }) {
  const { open, setOpen, rootRef, popoverRef, popoverStyle } = useAnchoredPopover({
    closeOnEscape: true,
    closeOnOutside: true,
    anchorSelector: ".work-action-grip",
    placement: placeActionMenu,
  });

  function toggle(event) {
    event.preventDefault();
    event.stopPropagation();
    setOpen((value) => {
      const next = !value;
      if (next) onOpen?.();
      return next;
    });
  }

  // Close after a real action (link/button) fires; leave form controls
  // (the download-format select, a checkbox) open so one pick doesn't
  // dismiss the menu before a second click.
  function onPopoverClick(event) {
    if (event.target.closest("a, button")) setOpen(false);
  }

  const popover =
    open && typeof document !== "undefined"
      ? createPortal(
          <div
            className="work-action-popover"
            ref={popoverRef}
            role="menu"
            tabIndex={0}
            aria-label={label ? `Actions for ${label}` : "Actions"}
            style={popoverStyle || { visibility: "hidden" }}
            onClick={onPopoverClick}
            onKeyDown={(event) => {
              if (event.key === "Escape") setOpen(false);
            }}
            data-testid={`${testId}-popover`}
          >
            {children}
          </div>,
          document.body,
        )
      : null;

  return (
    <div className={`work-action-menu${className ? ` ${className}` : ""}`} ref={rootRef}>
      <button
        type="button"
        className="work-action-grip"
        aria-label={`Actions for ${label || "this title"}`}
        aria-haspopup="menu"
        aria-expanded={open}
        onClick={toggle}
        data-testid={`${testId}-grip`}
      >
        <span aria-hidden="true">⋮</span>
      </button>
      {popover}
    </div>
  );
}
