/**
 * Library card (ProfileMenu) placement — viewport-aware flip/clamp so the
 * full owner panel (Settings → Logout) stays on screen. Kept free of React
 * so it is unit-testable with plain rect objects, matching placeActionMenu.
 */

function finite(value, fallback = 0) {
  const number = Number(value);
  return Number.isFinite(number) ? number : fallback;
}

/**
 * Where the portaled Library card panel sits relative to the chip.
 *
 * Prefer opening below the trigger (topbar). Flip above when that fits better;
 * always clamp into the viewport and expose maxHeight so CSS can scroll when
 * the panel is taller than the remaining space (phone + tabbar).
 * Right-aligns to the chip (trigger lives in `.topbar-end`).
 */
export function placeProfileMenu(anchor, menu) {
  const margin = 8;
  if (typeof window === "undefined") {
    return { top: `${margin}px`, left: `${margin}px` };
  }
  const viewW = finite(window.innerWidth);
  const viewH = finite(window.innerHeight);
  const menuWidth = finite(menu?.width);
  const menuHeight = finite(menu?.height);
  const anchorTop = finite(anchor?.top);
  const anchorBottom = finite(anchor?.bottom);
  const anchorRight = finite(anchor?.right);

  const below = anchorBottom + margin;
  const spaceBelow = Math.max(0, viewH - below - margin);
  const spaceAbove = Math.max(0, anchorTop - margin * 2);
  // Prefer below the chip (topbar). Flip only when above clearly fits better.
  const openBelow = menuHeight <= spaceBelow || spaceBelow >= spaceAbove;
  let top;
  let maxHeight;
  if (openBelow) {
    top = below;
    maxHeight = Math.max(120, spaceBelow);
    // If a short measured height still wouldn't fit, pin into the viewport.
    if (top + Math.min(menuHeight, maxHeight) > viewH - margin) {
      top = Math.max(margin, viewH - margin - Math.min(menuHeight, maxHeight));
      maxHeight = Math.max(120, viewH - top - margin);
    }
  } else {
    maxHeight = Math.max(120, spaceAbove);
    const used = Math.min(menuHeight, maxHeight);
    top = Math.max(margin, anchorTop - margin - used);
  }

  const left = Math.max(margin, Math.min(anchorRight - menuWidth, viewW - menuWidth - margin));

  return {
    top: `${top}px`,
    left: `${left}px`,
    maxHeight: `${maxHeight}px`,
  };
}
