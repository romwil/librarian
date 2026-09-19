/** Book → audiobook companion CTAs for work page / peek. */

import { findHref } from "./find.js";
import { workListenPath } from "./listen.js";

export function audiobookFindHref(find = {}) {
  if (!find || typeof find !== "object") return "/find?kind=audiobook";
  return findHref({ ...find, kind: "audiobook" });
}

export function companionAudiobookView(audiobook = null) {
  if (!audiobook || !audiobook.applicable) {
    return { show: false, shelved: null, listenHref: "", findHref: "", primaryLabel: "", secondaryLabel: "" };
  }
  const shelved = audiobook.shelved || null;
  const find = audiobookFindHref(audiobook.find || {});
  if (shelved?.id) {
    return {
      show: true,
      shelved,
      listenHref: workListenPath(shelved.id),
      findHref: find,
      primaryLabel: "Listen",
      secondaryLabel: "Audiobook on the shelves",
    };
  }
  return {
    show: true,
    shelved: null,
    listenHref: "",
    findHref: find,
    primaryLabel: "Find audiobook",
    secondaryLabel: "Available to Find",
  };
}
