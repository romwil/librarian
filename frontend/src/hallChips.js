/** Hall chip row: kinds with a count, then named shelves. */

import { browseHref } from "./browse.js";

export const KIND_CHIP_LABELS = {
  book: "Books",
  magazine: "Magazines",
  comic: "Comics",
  audiobook: "Audiobooks",
  music: "Music",
};

const KIND_ORDER = ["book", "magazine", "comic", "audiobook", "music"];

export function hallChipRow({ kind_counts = {}, named_shelves = [] } = {}) {
  const kinds = KIND_ORDER.map((kind) => ({
    kind,
    count: Number(kind_counts[kind] || 0),
  }))
    .filter((row) => row.count >= 1)
    .sort((a, b) => b.count - a.count || KIND_ORDER.indexOf(a.kind) - KIND_ORDER.indexOf(b.kind))
    .map((row) => ({
      key: `kind:${row.kind}`,
      label: KIND_CHIP_LABELS[row.kind],
      count: row.count,
      href: browseHref({ kind: row.kind }),
    }));
  const shelves = (Array.isArray(named_shelves) ? named_shelves : [])
    .filter((shelf) => Number(shelf?.work_count || 0) >= 1 && String(shelf?.id || "").trim())
    .map((shelf) => ({
      key: `shelf:${shelf.id}`,
      label: String(shelf.name || "Shelf").trim() || "Shelf",
      count: Number(shelf.work_count),
      href: browseHref({ shelf: shelf.id }),
    }));
  return [...kinds, ...shelves];
}
