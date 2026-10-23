/**
 * Whether a pointer/mouse event belongs to `root`.
 *
 * Chrome/WebKit retarget `<input type="range">` thumb (and some label
 * activations) onto `document`, so `event.target` and `composedPath()` both
 * miss the menu even when the gesture is over it. `composedPath` is a positive
 * signal only — a path that misses `root` must still hit-test coordinates.
 */
export function pointerEventInsideNode(event, root, locate = defaultLocate) {
  if (!root || !event) return false;

  try {
    const path = typeof event.composedPath === "function" ? event.composedPath() : [];
    if (Array.isArray(path) && path.includes(root)) return true;
  } catch {
    // Synthetic events may throw from composedPath().
  }

  const target = event.target;
  if (nodeInside(root, target)) return true;

  const x = Number(event.clientX);
  const y = Number(event.clientY);
  if (!Number.isFinite(x) || !Number.isFinite(y)) return false;

  const stacked = locate(x, y) || [];
  return stacked.some((node) => node === root || nodeInside(root, node));
}

function nodeInside(root, node) {
  if (!node || typeof root.contains !== "function") return false;
  if (node === root) return true;
  try {
    return root.contains(node);
  } catch {
    return false;
  }
}

function defaultLocate(x, y) {
  if (typeof document === "undefined") return [];
  if (typeof document.elementsFromPoint === "function") {
    return document.elementsFromPoint(x, y);
  }
  if (typeof document.elementFromPoint === "function") {
    const top = document.elementFromPoint(x, y);
    return top ? [top] : [];
  }
  return [];
}
