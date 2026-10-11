/** One verb cluster for a shelved book: Read, Listen, Download, or Want. */

import { audiobookFindHref } from "./audiobookCompanion.js";
import { searchHref } from "./find.js";
import { workListenPath } from "./listen.js";
import { workDownloadUrl, workReaderPath } from "./reader.js";

export function canManageWanted(role) {
  return role === "owner" || role === "op";
}

function hidden() {
  return {
    show: false,
    verb: "",
    chip: "",
    note: "",
    readHref: "",
    downloadHref: "",
    listenHref: "",
    searchHref: "",
    findHref: "",
    canAdd: false,
    canDismiss: false,
    wantedId: "",
    addBody: null,
  };
}

function shelfSearchHref(work, find = {}) {
  return searchHref({
    kind: "audiobook",
    title: find.title || work.title || "",
    author: find.author || work.author || "",
    isbn: find.isbn || work.isbn || "",
  });
}

/**
 * Availability for a book already on the shelf.
 * Listen wins when a companion audiobook is shelved.
 * Wanted is the miss, or an open Wanted row. A dismissal hides the prompt.
 */
export function bookAvailability({ work = {}, audiobook = null, wanted = null, role = "reader", beyond = false } = {}) {
  if (beyond || work.gap || work.kind === "gap") return hidden();
  if (work.kind !== "book" || !work.id) return hidden();

  const audio = audiobook || work.audiobook || null;
  const row = wanted || work.wanted || null;
  if (!audio || audio.applicable === false) return hidden();

  const manage = canManageWanted(role);
  const readHref = workReaderPath(work.id);
  const downloadHref = workDownloadUrl(work.id);
  const shelved = audio.shelved || null;
  const dismissed = row?.status === "dismissed";
  const openRow = row && row.id && !dismissed ? row : null;

  if (shelved?.id) {
    return {
      show: true,
      verb: "listen",
      chip: "Listen",
      note: "",
      readHref,
      downloadHref,
      listenHref: workListenPath(shelved.id),
      searchHref: "",
      findHref: "",
      canAdd: false,
      canDismiss: false,
      wantedId: "",
      addBody: null,
    };
  }

  if (dismissed) {
    return {
      show: true,
      verb: "read",
      chip: "Read",
      note: "",
      readHref,
      downloadHref,
      listenHref: "",
      searchHref: "",
      findHref: "",
      canAdd: false,
      canDismiss: false,
      wantedId: "",
      addBody: null,
    };
  }

  const find = audio.find || {};
  return {
    show: true,
    verb: "want",
    chip: "Wanted",
    note: openRow?.status === "asked" ? "Asked" : "The audiobook is wanted",
    readHref,
    downloadHref,
    listenHref: "",
    searchHref: shelfSearchHref(work, find),
    findHref: audiobookFindHref(find),
    canAdd: manage && !openRow,
    canDismiss: manage && Boolean(openRow?.id),
    wantedId: openRow?.id || "",
    addBody: {
      work_id: work.id,
      title: work.title || "",
      author: work.author || "",
      isbn: work.isbn || "",
      kind: "audiobook",
    },
  };
}
