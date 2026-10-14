import { findHref, searchHref } from "./find.js";
import { workListenPath } from "./listen.js";
import { workDownloadUrl, workReaderPath } from "./reader.js";

function text(value) {
  return String(value || "").trim();
}

export function notedQuery(item = {}, bag = {}) {
  return {
    q: text(bag.q),
    kind: text(bag.kind || item.kind),
    title: text(bag.title || item.title),
    author: text(bag.author || item.author),
    isbn: text(bag.isbn || item.isbn),
  };
}

export function notedSearchHref(item = {}) {
  return searchHref(notedQuery(item, item.search || {}));
}

export function notedFindHref(item = {}) {
  return findHref(notedQuery(item, item.find || {}));
}

export function notedWantedBody(item = {}, kind) {
  const wanted = item.wanted || {};
  return {
    title: text(wanted.title || item.title),
    author: text(wanted.author || item.author),
    isbn: text(wanted.isbn || item.isbn),
    kind: text(kind || wanted.kind || item.kind || "book"),
  };
}

function ownedStub(stub) {
  const id = text(stub?.id);
  if (!id) return null;
  return { id, href: `/works/${encodeURIComponent(id)}` };
}

/** Book and audiobook actions for one noted card. Owned formats link to the shelf. */
export function notedFormatActions(item = {}) {
  const book = ownedStub(item.shelved);
  const audio = ownedStub(item.shelved_audiobook);
  return ["book", "audiobook"].map((kind) => {
    const owned = kind === "audiobook" ? audio : book;
    if (owned) {
      const book = kind === "book";
      return {
        kind,
        owned: true,
        label: "On the shelf",
        href: owned.href,
        listenHref: kind === "audiobook" ? workListenPath(owned.id) : "",
        readHref: book ? workReaderPath(owned.id) : "",
        downloadHref: book ? workDownloadUrl(owned.id) : "",
      };
    }
    return {
      kind,
      owned: false,
      label: `Add to Wanted · ${kind}`,
      href: "",
      listenHref: "",
      readHref: "",
      downloadHref: "",
    };
  });
}
