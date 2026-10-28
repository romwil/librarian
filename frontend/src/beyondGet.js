/** Save a Usenet pick without talking to SABnzbd.

Get files a Wanted row, then an Asked slip when the hit has a guid.
Confirm on Downloads / Queue is what sends the NZB.
*/

import { api } from "./api.js";

export function wantedBodyFromHit(item = {}) {
  const kind = item.kind && item.kind !== "gap" ? item.kind : "book";
  return {
    work_id: item.work_id || "",
    title: item.book_title || item.title || "",
    author: item.author || "",
    isbn: item.isbn || "",
    kind,
  };
}

export function askHitFromItem(item = {}) {
  const category = item.category;
  return {
    guid: item.guid || item.indexer_guid || "",
    title: item.title || item.book_title || "",
    author: item.author || "",
    isbn: item.isbn || "",
    kind: item.kind || "",
    download_url: item.download_url || "",
    host_id: item.host_id || "",
    category: category != null && category !== "" ? String(category) : "",
    book_title: item.book_title || "",
    category_name: item.category_name || "",
  };
}

export function beyondGetPhase({ busy = false, queued = false } = {}) {
  if (queued) return "queued";
  if (busy) return "getting";
  return "idle";
}

export function beyondGetLabel(phase) {
  if (phase === "queued") return "Queued";
  if (phase === "getting") return "Getting…";
  return "Get";
}

/**
 * Persist a beyond / Usenet pick. Never calls /api/request (owner/op that path queues SAB).
 */
export async function saveBeyondGet(item, apiFns = {}) {
  const addWanted = apiFns.addWanted || ((body) => api.addWanted(body));
  const askWanted = apiFns.askWanted || ((id, hit) => api.askWanted(id, hit));
  const body = wantedBodyFromHit(item);
  if (!body.title && !body.isbn) {
    throw new Error("This result is missing a title.");
  }
  const hit = askHitFromItem(item);
  const added = await addWanted(hit.guid ? { ...body, hit } : body);
  const wanted = added?.item;
  if (!wanted?.id) {
    throw new Error("The house could not save that pick.");
  }
  if (wanted.status === "asked") {
    return { wanted, jobStatus: "asked" };
  }
  if (!hit.guid) {
    return { wanted, jobStatus: "saved" };
  }
  const asked = await askWanted(wanted.id, hit);
  return { wanted: asked?.item || wanted, jobStatus: "asked" };
}
