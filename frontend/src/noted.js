import { findHref, searchHref } from "./find.js";

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
