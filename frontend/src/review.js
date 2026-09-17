export function fieldsFromWork(work) {
  return {
    title: work.title || "",
    author: work.author || "",
    kind: work.kind || "book",
    isbn: work.isbn || "",
    series_name: work.series_name || "",
    series_index: work.series_index || "",
    year: work.year || "",
    folder: work.folder_path || work.storage_path || "",
  };
}

export function applyBodyFromDraft(draft) {
  const body = {
    title: draft.title,
    author: draft.author,
    kind: draft.kind,
    isbn: draft.isbn,
    series_name: draft.series_name,
    series_index: draft.series_index,
    folder: draft.folder,
  };
  if (draft.year !== "" && draft.year != null) {
    const year = Number(draft.year);
    if (!Number.isNaN(year)) body.year = year;
  }
  return body;
}

export function reviewReasonCopy(reason) {
  if (reason === "no_payload") {
    return "No book, comic, or audio file at this path. Apply cannot invent a payload — point the folder at files this Librarian can read, set SAB complete root to map /downloads, or Skip.";
  }
  if (reason === "unknown_identity") {
    return "Identity is missing. Fill title, author, ISBN or series/issue, then Apply.";
  }
  if (reason === "low_confidence") {
    return "Identify was unsure. Confirm or correct the fields, then Apply.";
  }
  if (reason === "unexpected_kind") {
    return "Kind does not match a library shelf. Pick book, magazine, comic, audiobook, or music.";
  }
  if (reason === "extra_files") {
    return "Extra files in the complete folder. Confirm the identity and Apply to file what is there.";
  }
  if (reason === "convert_failed") {
    return "A conversion is still needed (PDF book or CBR comic). Apply retries once files are readable.";
  }
  if (reason === "collision") {
    return "Collision — a file already exists at the library destination (duplicate path or identity). Librarian will not silent-overwrite.";
  }
  return "Unexpected item in the bagging area. Confirm identity and the complete folder, then Apply or Skip.";
}

/** Extra guidance under collision slips (Skip vs Apply). */
export function collisionActionCopy() {
  return "Skip keeps what’s already on the shelf and dismisses this slip. Apply will not overwrite — change title, author, series, or folder so the destination is free, then Apply.";
}

const COLLISION_DRAFT_KEYS = ["title", "author", "kind", "isbn", "series_name", "series_index", "folder"];

/** True when collision draft still matches the parked work (Apply would 400). */
export function collisionDraftUnchanged(draft, work) {
  const base = fieldsFromWork(work || {});
  const next = draft || base;
  return COLLISION_DRAFT_KEYS.every((key) => String(next[key] ?? "") === String(base[key] ?? ""));
}

/** Apply is allowed once identity/folder changes enough to seek a free destination. */
export function collisionApplyAllowed(reason, draft, work) {
  if (reason !== "collision") return true;
  return !collisionDraftUnchanged(draft, work);
}

/** One-line Queue copy for job status `review` → household **Needs you**. */
export function queueReviewReasonCopy(reason) {
  if (reason === "no_payload") {
    return "No readable book, comic, or audio file — open Review.";
  }
  if (reason === "unknown_identity") {
    return "Identity unclear — open Review to name it.";
  }
  if (reason === "low_confidence") {
    return "Identify was unsure — confirm it in Review.";
  }
  if (reason === "unexpected_kind") {
    return "Wrong shelf kind — pick one in Review.";
  }
  if (reason === "extra_files") {
    return "Extra files in the dump — confirm in Review.";
  }
  if (reason === "convert_failed") {
    return "Conversion still needed — open Review.";
  }
  if (reason === "collision") {
    return "Already on the shelf at that path — Open Review.";
  }
  return "Waiting in Review — the house isn’t sure how to shelve this.";
}
