import { useEffect } from "react";

/**
 * Set `document.title` and move keyboard focus to the page `h1` (tabIndex -1).
 * Route components call this once with a stable title.
 */
export default function usePageTitle(title) {
  useEffect(() => {
    if (!title) return undefined;
    const previous = document.title;
    document.title = title;
    return () => {
      document.title = previous;
    };
  }, [title]);

  useEffect(() => {
    if (!title) return undefined;
    const heading = document.querySelector("main h1, #main h1, h1");
    if (!heading) return undefined;
    if (!heading.hasAttribute("tabindex")) heading.tabIndex = -1;
    heading.focus({ preventScroll: true });
    return undefined;
  }, [title]);
}
