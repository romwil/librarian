/**
 * Stacks vs Favorites active-state for the reader nav and phone tab bar.
 * `/browse?shelf=favorites` highlights Favorites only; any other `/browse`
 * (any other query, or none) highlights Stacks. Ops links are untouched.
 */
export function stacksNavState(pathname, search = "") {
  const onBrowse = String(pathname || "") === "/browse";
  if (!onBrowse) return { stacks: false, favorites: false };
  const params = new URLSearchParams(String(search || "").replace(/^\?/, ""));
  const favorites = String(params.get("shelf") || "").trim().toLowerCase() === "favorites";
  return { stacks: !favorites, favorites };
}
