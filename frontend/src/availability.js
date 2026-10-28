/** One verb cluster for a shelved book: Read, Listen, Download, or Want. */

import { audiobookFindHref } from "./audiobookCompanion.js";
import { isInboundJob } from "./cover.js";
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
    status: "",
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

function wantedBody(work) {
  const kind = work.kind && work.kind !== "gap" ? work.kind : "book";
  return {
    work_id: work.id || "",
    title: work.title || "",
    author: work.author || "",
    isbn: work.isbn || "",
    kind,
  };
}

/**
 * List and card footers name the work that is there.
 * A missing companion format (verb "want") stays on the work page.
 */
export function forListCard(view) {
  if (!view?.show || view.verb === "want") return hidden();
  return view;
}

/**
 * Availability for a book already on the shelf.
 * Listen wins when a companion audiobook is shelved.
 * Wanted is the miss, or an open Wanted row. A dismissal hides the prompt.
 * Pass the result through forListCard before rendering a list or cover footer.
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
      status: "On the shelf",
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
      status: "On the shelf",
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
    status: "On the shelf",
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

function beyondSaved({ work = {}, role = "reader" } = {}) {
  const manage = canManageWanted(role);
  const asked = work.job_status === "asked" || work.wanted?.status === "asked";
  if (asked) {
    return {
      ...hidden(),
      show: true,
      status: "Asked",
      verb: "Queued",
      chip: "Asked",
      canAdd: false,
    };
  }
  if (isInboundJob(work.job_status)) {
    return {
      ...hidden(),
      show: true,
      status: "On the way",
      verb: "",
      chip: "On the way",
    };
  }
  if (work.wanted?.id && work.wanted?.status !== "dismissed") {
    return {
      ...hidden(),
      show: true,
      status: "Queued",
      verb: "Queued",
      chip: "Queued",
      canAdd: false,
    };
  }
  return {
    ...hidden(),
    show: true,
    status: "Not on the shelf",
    verb: manage ? "Get" : "Ask the house",
    chip: manage ? "Get" : "Ask the house",
    canAdd: manage,
    addBody: wantedBody(work),
  };
}

/**
 * Status + one verb for any catalog kind.
 * On the shelf → Read or Listen. Not on the shelf → Get (owner/op) or Ask the house.
 * Asked / Queued / On the way / Needs you replace Get.
 */
export function catalogStatus({ work = {}, role = "reader", beyond = false } = {}) {
  if (work.gap || work.kind === "gap") return hidden();

  const manage = canManageWanted(role);
  const kind = work.kind || "book";
  const addBody = wantedBody(work);

  if (work.review_state === "needs_review" || work.job_status === "review") {
    return {
      ...hidden(),
      show: true,
      status: "Needs you",
      verb: "",
      chip: "Needs you",
    };
  }

  if (beyond || !work.id) {
    return beyondSaved({ work, role });
  }

  if (work.job_status === "asked") {
    return {
      ...hidden(),
      show: true,
      status: "Asked",
      verb: "",
      chip: "Asked",
    };
  }
  if (isInboundJob(work.job_status)) {
    return {
      ...hidden(),
      show: true,
      status: "On the way",
      verb: "",
      chip: "On the way",
    };
  }

  const listen = kind === "audiobook";
  return {
    ...hidden(),
    show: true,
    status: "On the shelf",
    verb: listen ? "Listen" : kind === "music" ? "" : "Read",
    chip: listen ? "Listen" : kind === "music" ? "On the shelf" : "Read",
    readHref: listen || kind === "music" ? "" : workReaderPath(work.id),
    listenHref: listen ? workListenPath(work.id) : "",
  };
}
