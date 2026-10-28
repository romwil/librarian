import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const srcRoot = join(dirname(fileURLToPath(import.meta.url)), "..");

function inline(path, seen) {
  if (seen.has(path)) return "";
  seen.add(path);
  const text = readFileSync(path, "utf8");
  return text.replace(/@import\s+"([^"]+)";/g, (_, rel) => inline(join(dirname(path), rel), seen));
}

/** The whole SPA stylesheet as the browser sees it: styles.css with every @import inlined in order. */
export function readStyles() {
  return inline(join(srcRoot, "styles.css"), new Set());
}
